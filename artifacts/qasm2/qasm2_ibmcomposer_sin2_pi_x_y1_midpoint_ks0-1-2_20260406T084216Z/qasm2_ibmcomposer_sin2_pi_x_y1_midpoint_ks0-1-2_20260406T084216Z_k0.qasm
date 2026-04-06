OPENQASM 2.0;
include "qelib1.inc";

qreg q[3];
creg c[3];

// IBM Composer-compatible circuit for k=0: Q^k A |000>

// A: state preparation
h q[0];
h q[1];
ry(0.7853981633974483) q[2];
ry(0.7853981633974483) q[2];
cx q[0],q[2];
ry(-0.7853981633974483) q[2];
cx q[0],q[2];
ry(0.7853981633974483) q[2];
cx q[1],q[2];
ry(-0.7853981633974483) q[2];
cx q[1],q[2];
ry(-0.7853981633974482) q[2];
cx q[1],q[2];
ry(0.7853981633974482) q[2];
cx q[1],q[2];
cx q[0],q[1];
ry(0.7853981633974482) q[2];
cx q[1],q[2];
ry(-0.7853981633974482) q[2];
cx q[1],q[2];
cx q[0],q[1];

// Measurement
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
