#!/usr/bin/env python3
"""
PyHyCon -- a Python Hybrid Controller interface.

Note that the IO::HyCon Perl module is the reference implementation
that is maintained by the HyConAVR firmware author (Bernd).

While this implementation tries to be API-compatible with the reference
implementation, it tries to be minimal/low-level and won't implement any
client-side luxury (such as address mapping). It is the task of the
user to implement something high-level ontop of this.

Furthermore, this single-file module currently does not (yet) depend
on PySerial or similar. This is because it was mainly texted against
textual output or TCP/IP communication with the HyCon microcontroller.
It is up to the user to ensure proper communication. A few examples
are given at the end of this file.

(c) Sven Köppel 2019, Dual licensed with GPLv2, BSD
"""

# All these modules are Python internals
import sys, re, logging, time
from collections import namedtuple
from copy import deepcopy

#logging.basicConfig(level=logging.INFO) # only for testing
log = logging.getLogger('HyCon') # or __name__

def ensure(var, **q):
    "Our Assert function. Should probably use inspect.stack() or traceback.extract_stack() to get original varname"
    basemsg=f"Got {var=}" if not 'basemsg' in q else q['basemsg']
    if 'eq' in q and not var == q['eq']: raise ValueError(f"{basemsg}, but should be '{q['eq']}'")
    if 're' in q and not re.match(q['re'], var): raise ValueError(f"{basemsg}, but that doesn't match regexp '{q['re']}'")
    if 'inrange' in q and not (var >= q['inrange'][0] and var <= q['inrange'][1]): raise ValueError(f"{basemsg}, but it is not in range{q['inrange']}.")
    if 'within' in q and not var in q['within']: raise ValueError(f"{basemsg}, but it is none of {q['within']}.")
    if 'length' in q and not len(var)==q['length']: raise ValueError(f"{basemsg}, of {len(var)=} but expected to be len(var)={q['length']}.")
    if 'isa' in q and not isinstance(var, q['isa']): raise ValueError(f"{basemsg}, which is of {type(var)=} but expected  type {q['isa']}.")

class expect:
    def __init__(self, **q): self.q=q
    def __call__(self, r): # r: HyConRequest
        q = deepcopy(self.q);
        q['basemsg'] = f"Unexpected response: Command {r.command} yielded '{r.response}'"
        ensure(r.response, **q)
        mapper = q['as'] if 'as' in q else lambda x:x # id
        try:
            if 'ret' in q: return mapper(re.match(q['re'], r.response).groupdict()[ q['ret'] ])
            if 'split' in q: return map(mapper, re.split(q['split'], r.response))
            if 're' in q and not 'as' in q: return re.match(q['re'], r.response)
            return mapper(r.response)
        except ValueError:  raise ValueError(f"{basemsg} but cannot be casted/mapped to {mapper}")
    def __str__(self): return "expect(%s)"%str(self.q)[1:-1].replace("'",'')

def wont_implement(reason):
    def not_implemented(*v,**kw): raise NotImplementedError(reason)
    not_implemented.__doc__ = f"Not implemented because {reason}"
    return not_implemented

class HyConRequest:
    def __init__(self, command, expected_response=None):
        self.executed = False
        self.command = command
        self.expected_response = expect(re=expected_response) if isinstance(expected_response, str) else expected_response
        
    def __str__(self):
        return f"HyConRequest({self.command}, {self.expected_response}, {self.executed=}, "+\
            f"response={self.response if hasattr(self, 'response') else 'n.a.'}, "+\
            f"reply={self.reply if hasattr(self, 'reply') else 'n.a.'})"
        
    def write(self, hycon):
        if self.executed:
            raise ValueError("Shall not execute same command twice.")
        self.executed = True
        log.info(f"Sending [{self.command}]")
        hycon.fh.write(self.command)
        return self # chainable
    
    def read(self, hycon, expected_response=None, read_again=False):
        "Reads from hycon.fh, "
        if not expected_response: expected_response = self.expected_response
        if hycon.unidirectional:
            log.debug("Unidirectional channel, skipping reading from HyCon...")
            return self # chainable
        if not expected_response:
            log.info("No response expected, skipping reading from HyCon...")
            return self # chainable
        log.info(f"Waiting for response {expected_response} ... ")
        if read_again or not hasattr(self, "response"):
            self.response = hycon.fh.readline().strip() # Note: The HyConAVR always answers with a full line.
        if not self.response:
            raise ValueError(f"No Response from Hybrid controller! Command was '{self.command}'")
        self.reply = expected_response(self) # "Reply" is the highlevel, mapped answer
        return self # always chainable


class HyCon:
    "Low-Level Hybrid Controller OOP interface, similar to the Perl Hybrid controller."
    
    DIGITAL_OUTPUT_PORTS = 8
    DIGITAL_INPUT_PORTS = 8
    DPT_RESOLUTION = 10
    XBAR_CONFIG_BYTES = 10
    
    def __init__(self, fh, unidirectional=False):
        """
        Expects fh to be an IOHandler. This could be an open file,
        a (unix/inet) domain socket, a special device (serial port),
        some serial port library, etc.
        
        Make sure you disable output buffering (on print/write to fh), since commands do
        not end with newlines. Responses from the uC always end with newlines.
        
        If unidirectional is set, PyHyCon won't try to read from fh. Any
        read checks and mappings will be skipped and HyConRequest.read()
        will always return None.
        
        Important: We don't send anything at construction time, unless the
        reference implementation. Call reset() on yourself if you feel to do
        so.
        """
        self.fh = fh
        self.unidirectional = unidirectional
        if unidirectional: log.info(f"Won't make any attempt to read from the HyCon at {fh}")
    
    def query(self, *args, **kwargs):
        "Create a request, run it and check the reply"
        return HyConRequest(*args, **kwargs).write(self).read(self)
    
    def command(*args, help=None, **kwargs):
        "Return a method which, when called, creates a request, runs it and checks the reply"
        method = lambda self: self.query(*args, **kwargs)
        method.__doc__ = help
        return method
    
    ic               = command('i', '^IC',            help="Switch AC to IC-mode")
    op               = command('o', '^OP',            help="Switch AC to OP-mode")
    halt             = command('h', '^HALT',          help="Switch AC to HALT-mode")
    disable_ovl_halt = command('a', '^OVLH=DISABLED', help="Disable HALT-on-overflow")
    enable_ovl_halt  = command('A', '^OVLH=ENABLED',  help="Enable HALT-on-overflow")
    disable_ext_halt = command('b', '^EXTH=DISABLED', help="Disable external HALT")
    enable_ext_halt  = command('B', '^EXTH=ENABLED',  help="Enable external HALT")
    repetitive_run   = command('e', '^REP-MODE',      help="Switch to RepOp")
    single_run       = command('E', '^SINGLE-RUN',    help="One IC-OP-HALT-cycle")
    pot_set          = command('S', '^PS',            help="Activate POTSET-mode")

    def single_run_sync(self):
        "Synchronous run (finishes after a single run finished). Return value is true if terminated by ext. halt condition"
        q = self.query('F', '^SINGLE-RUN')
        timeout = 1.1 * (self.ictime + self.optime) # raises error if set_ic_time/set_op_time not called before
        time.sleep(timeout / 1000)
        res = q.read(self, expect(re='^EOSR(HLT)?'), read_again=True)
        was_terminated_by_ext_halt_condition = res.reply.groups()[0]=="HLT" # EOSRHLT
        return was_terminated_by_ext_halt_condition
    
    def set_ic_time(self, ictime):
        ensure(ictime, within=range(0,999999)); self.ictime = ictime
        return self.query('C%06d' % ictime, expect(eq=f"T_IC={ictime}"))
    
    def set_op_time(self, optime):
        ensure(optime, inrange=(0,999999)); self.optime = optime
        return self.query('c%06d' % optime, expect(eq=f"T_OP={optime}"))
    
    def get_data(self):
        q = self.query('l', "^No data!|.*$")
        if q.response == "No data!": return None
        data = []
        while True:
            resp = q.read(self, expect(re="^([-\d\.\s]*|EOD)*$"), read_again=True).response.split()
            if "EOD" in resp: break
            data.append(list(map(float, resp)))
        return data
    
    def read_element_by_address(self, address):
        "Expecting 16-bit address as integer"
        ensure(address, isa=int)
        response_match = self.query("g%04X" % address, r"(?P<value>.+)\s+(?P<id>.+)").reply
        return response_match.groupdict() # return the dictionary value-> ..., id-> ..., caveat, should be all numeric!?
    
    def set_ro_group(self, addresses):
        for a in addresses: ensure(a, isa=int)
        return self.query("G" + ";".join([f"{a:04X}" for a in addresses]) + ".")
    
    read_ro_group = command('f', expect(split=";", type=float))
    read_digital = command("R", expect(re="^"+"\d\s"*(DIGITAL_INPUT_PORTS-1), split='', type=bool), help="Read digital inputs")
    
    def digital_output(self, port, state):
        "Set digital output pins of the Hybrid Controller"
        ensure(port, inrange=(0, self.DIGITAL_OUTPUT_PORTS)); ensure(state, isa=bool)
        return self.query(f"{'D' if state else 'd'}{port:1d}")

    def set_xbar(self, address, config):
        """Exactly {self.XBAR_CONFIG_BYTES*2} HEX-nibbles are required to config data."""
        ensure(address, isa=int); ensure(config, length=self.XBAR_CONFIG_BYTES*2)
        return self.query(f"X{address:04X}{config}", expect(eq="XBAR READY"))
    
    read_mpts = wont_implement("because it is just a high-level function which calls pot_set and iterates a list of potentiometer address/names.")
    
    def set_pt(self, address, number, value):
        "Set a digital potentiometer by address/number."
        ensure(value, inrange=(0,1))
        value = int(value * (2 ** self.DPT_RESOLUTION - 1)) # 0000 <= value <= 1023
        return self.query(f"P{address:04X}{number:02X}{value:04d}", expect(eq=f"P{address:X}.{number:X}={value:d}"))
    
    read_dpts = wont_implement("because it doesn't actually self.query the hardware but just ask the HC about its internal storage.")
    
    def get_status(self):
        response = self.query('s', '.*=.*,.*').reply.string # expecting something with commas :-)
        state = dict(items.split("=") for items in response.split(","))
        state['RO-GROUP'] = state['RO-GROUP'].split(";")
        state['DPTADDR'] = state['DPTADDR'].split(";") # don't resolve mapping
        return state

    get_op_time = command('t', expect(re="t_OP=(?P<time>-?\d*)", ret='time', to=float))
    reset = command('x', expect(eq='RESET'))

class serialdummy:
    "Dummy IOWrapper for testing HyCon.py without the actual hardware"
    def write(self, sth):     print(f"<< Sending [{sth}] to uC")
    def readline(self): return input("[type reply of uC]>> ")

class tcpsocket:
    "Wrapper for communicating with HyCon over TCP/IP"
    def __init__(self, host, port):
        from socket import socket # builtin
        self.s = socket()
        self.s.connect((host,port))
        self.fh = self.s.makefile(mode="rw", encoding="utf-8")
    def write(self, sth):
        "Expects sth to be a string"
        self.s.sendall(sth.encode("ascii"))
    def readline(self):
        # instead also: self.s.recv(123)
        return self.fh.readline()
        
if __name__ == "__main__":
    # Run these examples with an interactive python REPL to play with them:
    
    if 0:
        # example how to use PyHyCon with a microcontroller "simulator"
        ac = HyCon(serialdummy())    
        ac.set_ic_time(234)
        
    if 0:
        # example how to use PyHyCon only for writing firmware command
        ac = HyCon(sys.stdout, unidirectional=True)
        ac.set_ic_time(234)
    
    if 0:
        # example how to use PyHyCon over TCP/IP
        sock = tcpsocket("localhost", 12345)
        ac = HyCon(sock)
        ac.reset()
        ac.digital_output(3, True)
        ac.set_op_time(123)
        ac.set_xbar(0x0040, "0000000210840000781B")