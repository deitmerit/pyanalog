"""
C++ code generation
"""

from .ast import State, Symbol, topological_sort
from .computing_elements import cpp_impl

import textwrap, itertools

cpp_template = """\
// This code was generated by PyDDA.

#include <cmath> /* don't forget -lm for linking */
#include <cfenv> /* for feenableexcept */
#include <limits> /* for signaling NAN */
#include <cstdio>

constexpr double %(nan_name)s = std::numeric_limits<double>::signaling_NaN();

%(cpp_impl)s

// Time-evolved variables, actual "state" (in general dq/dt!=0)
struct %(state_type)s {
%(state_var_definition)s
%(dqdt_operators)s
};

// Auxiliary variables, derived from %(state_type)s, not evolved in time (dqdt=0)
struct %(aux_type)s  {
%(aux_var_definition)s
void set_to_nan() {
    %(aux_var_set_to_nan)s
}
};

/// Compute the equations as given in the dda file
/// It is actually %(dqdt_name)s = f(%(state_name)s, %(aux_name)s), or at least
/// (%(dqdt_name)s,%(aux_name)s) = f(%(state_name)s).
/// %(aux_name)s is only returned for debugging and controlling purposes of intermediate results
void f(%(state_type)s const &%(state_name)s, %(state_type)s &%(dqdt_name)s, %(aux_type)s &%(aux_name)s) {
%(aux_name)s.set_to_nan(); // only for debugging: ensure no use of uninitialized variables

%(equations)s
}

%(state_type)s
initial_data{ %(initial_data)s },
dt{ %(timestep_data)s };

%(state_type)s simulate_dda(%(state_type)s initial, int max_iterations, int modulo_write, int rk_order) {
%(state_type)s k1, k2, k3, k4, z, %(state_name)s=initial;
%(aux_type)s %(aux_name)s;

for(int iter = 0; iter < max_iterations; iter++) {
    switch(rk_order) {
        case 1:
            // Explicit Euler scheme
            f(%(state_name)s, k1, %(aux_name)s);
            %(state_name)s = %(state_name)s + k1*dt;
            break;
        case 2:
            // RK2 scheme
            f(%(state_name)s, k1, %(aux_name)s);
            f(%(state_name)s + k1*dt, k2, %(aux_name)s);
            %(state_name)s = %(state_name)s + (k1+k2)*dt*0.5;
            break;
        case 3:
            // Kutta's third order scheme 
            f(%(state_name)s, k1, %(aux_name)s);
            f(%(state_name)s + dt*k1*0.5, k2, %(aux_name)s);
            f(%(state_name)s + dt*k1*(-1.0) + dt*k2*2.0, k3, %(aux_name)s);
            %(state_name)s = %(state_name)s + (k1 + k2*4.0 + k3*1.0)*dt*(1./6.);
            break;
        case 4:
            // Classical RK4 scheme 
            f(%(state_name)s, k1, %(aux_name)s);
            f(%(state_name)s + dt*k1*0.5, k2, %(aux_name)s);
            f(%(state_name)s + dt*k2*0.5, k3, %(aux_name)s);
            f(%(state_name)s + dt*k3*1.0, k4, %(aux_name)s);
            %(state_name)s = %(state_name)s + (k1 + k2*2.0 + k3*2.0 + k4)*dt*(1./6.);
            break;
        default:
            exit(-42);
    }

    if(iter %% modulo_write == 0) {
        printf(%(writer_formatstring)s, %(writer_format_arguments)s);
    }
}

return %(state_name)s;
}

int main(int argc, char** argv) {
feenableexcept(FE_DIVBYZERO | FE_INVALID | FE_OVERFLOW);

puts(%(writer_header)s); // Write CSV header

int modulo_write = %(modulo_write)d,
    max_iterations = %(max_iterations)d,
    rk_order = %(rk_order)d;

simulate_dda(initial_data, max_iterations, modulo_write, rk_order);
}

"""


def to_cpp(state, writer_fields="All",
    modulo_write=20, max_iterations=30000, rk_order=1):
    """
    Allows for compiling DDA to a standalone C++ code.
    
    Will return a single string, the C++ code.
    
    TODO: Write some documentation :-)
    """

    indent = " "*5 # or tab, whatever you prefer - should be fit to cpp_template

    # Despite all user-chosen variable names are scoped within structs/classes, name
    # clashes are possible in some contexts. Therefore, the following names should be
    # chosen carefully.
    state_type, aux_type = "state_variables", "auxillaries"
    state_name, dqdt_name, aux_name, other_name = "_state", "_dqdt", "_aux", "_other"
    nan_name = "_nan_"

    state = state.name_computing_elements()

    # Thanks to named computing elements, can find all int(...) expressions
    # without searching, since they must come first.
    evolved_variables = sorted(filter(lambda var: state[var].head == "int", state))

    # prepare for prefixing all RHS variables
    struct_for = lambda name: state_name if name in evolved_variables else aux_name
    prefix_rhs = lambda el: Symbol(f"{struct_for(el.head)}.{el.head}") if el.is_variable() else el
    # Remove any const() which remained. Would be nicer to assert not having consts() at all.
    remove_const = lambda x: x.tail[0] if isinstance(x,Symbol) and x.head=="const" else x

    # rename reserved keywords in the C language
    #c_names = { "const": "constant", "int": "Int", "div": "Div" }
    #c_substitute = lambda head: c_names.get(head, head)
    #c_state = State({ var: map_heads(state[var], c_substitute) for var in state })

    # Extract int(..., timestep, initial_data) and rewrite reserved C keyword
    timesteps = {}
    initial_data = {}
    def map_and_treat_integrals(var):
        if not var in evolved_variables: return state[var]
        tail = state[var].tail
        if not len(tail) >= 3: raise ValueError("int(...) requires at least int(value, dt, ic)")
        timesteps[var] = remove_const(tail[-2])
        initial_data[var] = remove_const(tail[-1])
        return Symbol("Int", *tail[0:len(tail)-2])
    state = State({ var: map_and_treat_integrals(var) for var in state })

    # Sort ONLY aux variables. Check that they DO NOT have any
    # cyclic dependency, because this would crash any circuitery anyway.
    #
    # Then compute ALL aux variables BEFORE computing dqdt.
    # The order of dqdt should not be touched, as there CAN NOT be any
    # dependency, since dqdt.foo = int(state).
    #
    # The dependency is basically
    #   aux = function_of(aux, state)
    #   dqdt = function_of(aux, state)
    # and in the integration schema step
    #   state = function_of(dqdt)

    all_vars = sorted(set.union(*[set(map(str, state[k].all_variables())) for k in state], state))
    aux_variables = [ v for v in all_vars if not v in evolved_variables  ]

    # Linearize aux expressions by dependency sorting.
    dep_edge_list = state.dependency_graph()
    # Edge direction: (a,b) = [dependent variable a]--[depends on]-->[dependency b]
    aux_dep_edges = [ (a,b) for a,b in dep_edge_list if a in aux_variables and b in aux_variables ]
    #sorted_vars, cyclic_vars = topological_sort(dep_edge_list)
    sorted_aux_vars, cyclic_aux_vars = topological_sort(aux_dep_edges)
    #all_vars = sorted_vars + cyclic_vars
    # aux_variables = set(all_vars) - set(evolved_variables) but preserving sorting.

    # TODO: Make returnable or at least warn user!
    unneeded_auxers = set(aux_variables) - (set(sorted_aux_vars) | set(cyclic_aux_vars))

    # do the renaming *after* variable dependency analysis
    state = state.map_tails(remove_const)
    state = state.map_tails(prefix_rhs)
        
    # C-format lists of statements or so. Do indentation.
    J = lambda whatever: ", ".join(whatever)
    C = lambda whatever: textwrap.indent(whatever if isinstance(whatever, str) else  "\n".join(whatever), indent)
    CC = lambda whatevr: C(C(whatevr)) # two indentations ;-)
    varlist = lambda ctype, lst: C(textwrap.wrap(f"{ctype} {', '.join(lst)};", width=50))

    state_var_definition = varlist("double", evolved_variables)
    aux_var_definition = varlist("double", aux_variables)
    all_variables_as_string = C('"'+v+'",' for v in all_vars)

    # For debugging:
    aux_var_set_to_nan = C(f"{v} = {nan_name};" for v in aux_variables)

    initial_data = J(f"{initial_data[v]}" for v in evolved_variables)
    timestep_data = J(f"{timesteps[v]}" for v in evolved_variables)

    #state_assignments = lambda lst: C(f"{v} = {state[v]};" for v in lst)) if lst else C("/* none */")
    state_assignments = lambda lhs_struct,lst: [f"{lhs_struct}.{v} = {state[v]};" for v in lst] if lst else ["/* none */"]

    equations = []
    equations.append("// 1. Topologically sorted aux variables")
    equations += state_assignments(aux_name, sorted_aux_vars)
    equations.append("// 2. Cyclic aux variables")
    equations += state_assignments(aux_name, cyclic_aux_vars)
    equations.append("// 3. State variable changes (dqdt), finally")
    equations += state_assignments(dqdt_name, evolved_variables)
    equations.append("// 4. Unneeded auxilliary variables (maybe postprocessing, etc.)")
    equations += state_assignments(aux_name, unneeded_auxers)
    equations = C(equations)

    if writer_fields == "All":
        writer_fields = all_vars
    writer_header = '"'+" ".join(writer_fields)+'"'
    writer_format_arguments = J(f"{struct_for(v)}.{v}" for v in writer_fields)
    writer_formatstring = '"'+" ".join('%f' for v in writer_fields)+"\\n\""

    make_operator = lambda operator_symbol, other_type, a=True: [ \
        f"{state_type} operator{operator_symbol}(const {other_type} &{other_name}) const "+'{', \
        C(f"{state_type} {state_name};"), \
        C(f"{state_name}.{v} = {v} {operator_symbol} {other_name}{'.'+v if a else ''};" for v in evolved_variables), \
        C(f"return {state_name};"), \
        "}"]

    dqdt_operators = C(C(make_operator(s,o,a)) for s,(o,a) in
        itertools.product("*+", zip((state_type, "double"), (True,False))))

    output = cpp_template % {**locals(), **globals()}
    return output

# What follows are a few helper functions to make the usage nicer

def compile(code, basename, compiler="g++", compiler_output="a.out", options="-Wall"):
    "Simple helper function to nicely invoke a compiler"
    if system(f"{compiler} -o{compiler_output} {options} {basename}"): raise ValueError("Could not compile C source!")

def run(compiled_binary, scratch_file="test.csv"):
    if system(f"./{compiler_output} > {scratch_file}"): raise ValueError("Could not execute simulation!");
    # TODO: Could think about slurping STDOUt directly without scratch file.

