#!/usr/bin/env python3

import os

def sh(cmd):
    print(cmd)
    if os.system(cmd): raise ValueError(f"FAILED: {cmd}")

# Run the double pendulum
run_simulation = True
if run_simulation:
    sh("python -m dda  double-pendulum.dda C > double-pendulum.cpp")
    sh("g++ --std=c++17 -o double-pendulum.out double-pendulum.cpp")
    sh("./double-pendulum.out --max_iterations=15000 --modulo_write=10 > data.out")

from pylab import *

data = genfromtxt("data.out", names=True)

p1, p2 = data["p1"], data["p2"]
l1, l2 = 1, 1 # lengths of pendulums

#blowup = 20
#p1, p2 = p1.repeat(blowup), p2.repeat(blowup)
#t = tile( linspace(0, 2*pi, num=blowup), len(data))

w = 0.2
k = 40
r = int( len(data)/k )
#assert k*r == len(data), f"{k} x {r} != {len(data)}"

#t = tile(linspace(0, 2*pi, num=k), r)
t = arange(len(data))

l1 = sin(w*t) * ones_like(p1)
l2 = sin(w*t) * ones_like(p2)

#l1 = 1
#l2 = 1

x1 = l1*sin(p1)
y1 = l1*cos(p1)
x2 = l2*sin(p2) + x1 # 1*sin(p1)
y2 = l2*cos(p2) + y1 #1*cos(p1)

x2 = l2*sin(p2) + 1*sin(p1)
y2 = l2*cos(p2) + 1*cos(p1)

ion()
plot(x1, y1, color="green")
plot(x2, y2, color="blue")

savefig("double-pendulum.pdf")