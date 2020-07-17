"""
The DDA domain specific language, also refered to as "traditional dda",
is the C-like language invented by Bernd for his Perl'ish dda code.

Interestingly, traditional DDA files are a python subset and thus can
be easily parsed and generated by python syntax. That's why this file is
so short and little has to be done. That's also a primary reason why
DDA was rewritten in Python.
"""

class traditional_dda_exporter(exporter):
    """
    Export state to canonical dda file format (i.e. without all the python).
    """
    
    def run(self):
        # Not sure about scattered consts, maybe just remove them for the time being.
        remove_const = lambda x: x.tail[0] if isinstance(x,Symbol) and x.head=="const" else x
        state = self.state.map_tails(remove_const)
        # TODO: Treat constants better. They have deserved it!
        
        dda_lines = []
        dda_lines.append("# Canonical DDA file generated by PyDDA")
        dda_lines.append("")
        for k in sorted(state):
            dda_lines.append(f"{k} = {state[k]}")
        dda_lines.append("")
        
        self.output = "\n".join(dda_lines)


def read_traditional_dda(content, return_ordered_dict=False):
    """
    Read some traditional dda file. We use the Python parser (ast builtin package)
    for this job. This is possible because the DDA syntax is a python subset and
    the parser doesn't care about semantics, only syntax.
    Thanks to the ast builtin package, we can just transform the python AST to
    the Symbolic/State class data structures used in this module.
    
    If some of the assertions fail, you can debug your DDA file by inspecting
    the output of ast.parse(content) on iPython. You can also run the Python
    debugger (pdb) on this function, for instance in iPython:
    
    > %pdb
    > read_traditional_dda(file("foo.dda").read())
    
    Returns a state instance or OrderedDict, on preference.
    """
    import ast # python builtin
    tree = ast.parse(content)
    
    assert type(tree) == ast.Module, "I was expecting a whole file as content"
    assert type(tree.body) == list, "DDA file malformed, I was expecting a list of statements"
    assert all(type(f) == ast.Assign for f in tree.body), "DDA file malformed, I was expecting a list of assignments only"
    
    def arg2symbol(argument):
        "Transform some DDA function argument to the Symbol hierarchy"
        expr_as_str = ast.get_source_segment(content, argument) 
        if isinstance(argument, ast.Constant):
            return argument.value
        elif isinstance(argument, ast.Name):
            return argument.id
        elif isinstance(argument, ast.Call):
            return call2symbol(argument)
        else:
            raise TypeError(f"Don't understand argument '{expr_as_str}'")
    
    def call2symbol(statement):
        "Transform some Right Hand Side nested function call to Symbol hierarchy"
        expr_as_str = ast.get_source_segment(content, statement) # for debugging, can also print ast.dump(statement)
        assert type(statement) == ast.Call, f"Was expecting a simple f(x) call but got '{expr_as_str}'"
        assert len(statement.keywords) == 0, f"Did not expect pythonic keyword arguments f(x=bar) in '{expr_as_str}'"
        assert type(statement.func) == ast.Name, f"Dunno, what is {statement.func}?"
        head = statement.func.id
        tail = map(arg2symbol, statement.args)
        return Symbol(head, *tail)
    
    def ast_assignment_to_tuple(assign):
        line = ast.get_source_segment(content, assign) # for debugging, can also print ast.dump(assign)
        assert len(assign.targets)==1, f"Was expecting only a single assignment, but got '{line}'"
        assert type(assign.value) == ast.Call, f"DDA file malformed, expecting foo=call(bar), but got '{line}'."
        variable_name = assign.targets[0].id
        rhs = call2symbol(assign.value)
        return (variable_name, rhs)
    
    result = map(ast_assignment_to_tuple, tree.body)
    mapping = collections.OrderedDict(result)
    return mapping if return_dict else State(mapping)


