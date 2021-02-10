#
# Copyright (c) 2020 anabrid GmbH
# Contact: https://www.anabrid.com/licensing/
#
# This file is part of the DDA module of the PyAnalog toolkit.
#
# ANABRID_BEGIN_LICENSE:GPL
# Commercial License Usage
# Licensees holding valid commercial anabrid licenses may use this file in
# accordance with the commercial license agreement provided with the
# Software or, alternatively, in accordance with the terms contained in
# a written agreement between you and Anabrid GmbH. For licensing terms
# and conditions see https://www.anabrid.com/licensing. For further
# information use the contact form at https://www.anabrid.com/contact.
# 
# GNU General Public License Usage
# Alternatively, this file may be used under the terms of the GNU 
# General Public License version 3 as published by the Free Software
# Foundation and appearing in the file LICENSE.GPL3 included in the
# packaging of this file. Please review the following information to
# ensure the GNU General Public License version 3 requirements
# will be met: https://www.gnu.org/licenses/gpl-3.0.html.
# ANABRID_END_LICENSE
#

"""
The DDA domain specific language, also refered to as "traditional dda",
is the C-like language invented by Bernd for his Perl'ish dda code.

It basically reads as the following snippet:

::

    # Single-line comments are written like this

    dt = const(0.5)  # constants are defined like this
    y0 = const(1)

    z = mult(y, y)
    y = int(y, dt, y0)


As you see, variables do not even have to be introduced and can be
used in any order. There is only one data type, the *analog line signal*
which is basically a real number within a fixed interval.

.. note::

   Interestingly, traditional DDA files are a python subset and thus can
   be easily parsed and generated by python syntax. That's why the code
   of this PyDDA module is so short. That's also a primary reason why
   DDA was rewritten in Python.
   
Demonstration usage of this module:

>>> traditional_dda_document='''
... # Single-line comments are written like this
... 
... dt = const(0.5)  # constants are defined like this
... y0 = const(1)
... 
... z = mult(y, y)
... y = int(y, dt, y0)
... '''
>>> state = read_traditional_dda(traditional_dda_document)
>>> state
State({'dt': const(0.5), 'y': int(y, dt, y0), 'y0': const(1), 'z': mult(y, y)})
>>> print(to_traditional_dda(state))   # doctest: +NORMALIZE_WHITESPACE
# Canonical DDA file generated by PyDDA
<BLANKLINE>
dt = const(0.5)
y = int(y, dt, y0)
y0 = const(1)
z = mult(y, y)
<BLANKLINE>

   
"""

from . import clean, ast as dda # in order to explicitely write dda.Symbol, dda.State
import collections, sys, argparse, builtins, os, inspect # python included

def to_traditional_dda(state, cleanup=True, prefix="# Canonical DDA file generated by PyDDA\n", suffix="\n"):
    """
    Export state to canonical dda file format (i.e. without all the python).
    
    Returns the generated DDA file as string
    """
    
    if cleanup:
        # Not sure about scattered consts, maybe just remove them for the time being.
        remove_const = lambda x: x.tail[0] if isinstance(x,dda.Symbol) and x.head=="const" else x
        state = clean(state, target="dda").map_tails(remove_const)
        # TODO: Treat constants better. They have deserved it!

    dda_lines = []
    if prefix: dda_lines.append(prefix)
    for k in sorted(state):
        dda_lines.append(f"{k} = {state[k]}")
    if suffix: dda_lines.append(suffix)

    output = "\n".join(dda_lines)
    return output


def read_traditional_dda(content, return_ordered_dict=False):
    """
    Read some traditional dda file. We use the Python parser (``ast`` builtin)
    for this job. This is possible because the DDA syntax is a python subset and
    the parser doesn't care about semantics, only syntax.
    
    Thanks to the ``ast`` builtin package, we can just transform the python AST to
    the Symbolic/State class data structures used in this module.
    
    .. note::
    
       If some of the assertions fail, you can debug your DDA file by inspecting
       the output of ast.parse(content) on iPython. You can also run the Python
       debugger (pdb) on this function, for instance in iPython:
    
       >>> %pdb                                                  # doctest: +SKIP
       >>> read_traditional_dda(file("foo.dda").read())          # doctest: +SKIP
    
    Returns a state instance or OrderedDict, on preference.
    """
    import ast # python builtin
    tree = ast.parse(content)
    
    assert type(tree) == ast.Module, "I was expecting a whole file as content"
    assert type(tree.body) == list, "DDA file malformed, I was expecting a list of statements"
    assert all(type(f) == ast.Assign for f in tree.body), "DDA file malformed, I was expecting a list of assignments only"
    
    def expr2str(ast_obj):
        "Get source back; https://stackoverflow.com/questions/32146363/python-ast-abstract-syntax-trees-get-back-source-string-of-subnode"
        if hasattr(ast, "get_source_segment"): # Python >=3.8
            return ast.get_source_segment(content, ast_obj)
        else:
            return ast.dump(ast_obj) + " (Hint: Use Python >=3.8 to get source segment)"

    def arg2symbol(argument):
        "Transform some DDA function argument to the Symbol hierarchy"
        if isinstance(argument, ast.Constant):
            return argument.value
        elif isinstance(argument, ast.Name):
            return dda.Symbol(argument.id)
        elif isinstance(argument, ast.Call):
            return call2symbol(argument)
        elif isinstance(argument, ast.UnaryOp):
            # something like -1 is represented as ~ ast.USub(-1)
            return ast.literal_eval(argument)
        elif isinstance(argument, ast.Num):
            return argument.n
        else:
            raise TypeError(f"Don't understand argument type '{expr2str(argument)}'")
    
    def call2symbol(statement):
        "Transform some Right Hand Side nested function call to Symbol hierarchy"
        assert type(statement) == ast.Call, f"Was expecting a simple f(x) call but got '{expr2str(statement)}'"
        assert len(statement.keywords) == 0, f"Did not expect pythonic keyword arguments f(x=bar) in '{expr2str(statement)}'"
        assert type(statement.func) == ast.Name, f"Dunno, what is {statement.func}?"
        head = statement.func.id
        tail = map(arg2symbol, statement.args)
        return dda.Symbol(head, *tail)
    
    def ast_assignment_to_tuple(assign):
        assert len(assign.targets)==1, f"Was expecting only a single assignment, but got '{expr2str(assign)}'"
        assert type(assign.value) == ast.Call, f"DDA file malformed, expecting foo=call(bar), but got '{expr2str(assign)}'."
        variable_name = assign.targets[0].id
        rhs = call2symbol(assign.value)
        return (variable_name, rhs)
    
    result = map(ast_assignment_to_tuple, tree.body)
    mapping = collections.OrderedDict(result)
    return mapping if return_ordered_dict else dda.State(mapping)

def read_traditional_dda_file(filename, **kwargs):
    """
    Syntactic sugar for :meth:`read_traditional_dda`, so users can directly pass a filename
    if the have their DDA code in a file.
    """
    with open(filename, "r") as fh:
        content = fh.read()
    return read_traditional_dda(content, **kwargs)


def cli_exporter():
    """
    A Command Line Interface (CLI) for PyDDA.

    This CLI API does mainly what the old dda2c.pl script did, i.e.
    translating a (traditional) DDA file to C code. There are fewer
    options, because --iterations, --modulus and --variables are
    now runtime options for the generated C program.
    
    However, we can generate much more then C. Output is always text.
    
    Invocation is either ``python -m dda --help`` or ``python -m dda.dsl --help``
    anywhere from the system. ``setup.py`` probably also installed a
    ``pydda`` binary somewhere calling the same. You can also just
    call ``./dsl.py --help``.
    """
    int = builtins.int # just to go sure
    
    parser = argparse.ArgumentParser(description="PyDDA, the AST-based DDA compiler", epilog=inspect.getdoc(cli_exporter))

    parser.add_argument("circuit_file", nargs='?', type=argparse.FileType('r'), default=sys.stdin, help="DDA setup (traditional file). Default is stdin.")
    parser.add_argument("-o", "--output", nargs='?', type=argparse.FileType('w'), default=sys.stdout, help="Where to write exported code to. Default is stdout.")
    
    # case insensitive choices. Will be parsed by export() anyway
    parser.add_argument("format", choices=["c", "dda", "dot", "latex"], type=str.lower, help="File formats which can be generated")
    
    # The following is deprecated because it is now runtime information for the C++ code.
    #C = parser.add_argument_group(title="Arguments for C++ code generation (Only apply if --export=C)")
    #C.add_argument("-N", "--iterations", type=int, help="Number of integration steps to be performed")
    #C.add_argument("-m", "--modulus", type=int, help="Output a value every <modulus> iteration steps")
    #C.add_argument("-v", "--variables", nargs="*", help="List of variables to be plotted (comma seperated)")
    
    arg = parser.parse_args()
    
    dda_text = arg.circuit_file.read()
    state = read_traditional_dda(dda_text)
    exported_code = state.export(to=arg.format)
    print(exported_code, file=arg.output)
    
if __name__ == "__main__":
    cli_exporter()
