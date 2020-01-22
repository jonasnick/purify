#!/usr/bin/env python3

import sys
import hmac
import hashlib
import secrets
import copy
from math import ceil, log
import argparse

# Parameters generated using gen_params.sage for Curve25519
#P = 0x1000000000000000000000000000000014DEF9DEA2F79CD65812631A5CF5D3ED
#A = 95
#B = 78
#D = 2
#N1 = 0x100000000000000000000000000000004E9C306B81CF1C611587B3ED91288DAD
#N2 = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFDB21C351C4201D4B9A9D124728C31A2F

# Parameters generated using gen_params.sage for secp256k1
P = 115792089237316195423570985008687907852837564279074904382605163141518161494337
A = 118
B = 339
D = 5
N1 = 115792089237316195423570985008687907853146579067639158218940405176378157516777
N2 = 115792089237316195423570985008687907852528549490510650546269921106658165471899

# Parameters generated using gen_params.sage for BLS12-381
#P = 0x73EDA753299D7D483339D80809A1D80553BDA402FFFE5BFEFFFFFFFF00000001
#A = 245
#B = 46
#D = 5
#N1 = 0x73EDA753299D7D483339D80809A1D804942105BA15136AAC92458EF0CDB43949
#N2 = 0x73EDA753299D7D483339D80809A1D806135A424BEAE94D516DBA710D324BC6BB

# Parameters generated using gen_params.sage for BN(2,254)
#P = 0x2523648240000001BA344D8000000007FF9F800000000010A10000000000000D
#A = 209
#B = 140
#D = 2
#N1 = 0x2523648240000001BA344D80000000089C9DDF8B4198211E1005BEF4E673BA39
#N2 = 0x2523648240000001BA344D800000000762A12074BE67DF0331FA410B198C45E3

# Parameters generated using gen_params.sage for Ed448-Goldilocks
#P = 0x3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF7CCA23E9C44EDB49AED63690216CC2728DC58F552378C292AB5844F3
#A = 155
#B = 199
#D = 2
#N1 = 0x3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF61E19CF8AE93A7F6204DD85972E93B7A4C4733D057799E70F578D05B
#N2 = 0x3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF97B2AADADA0A0E9D3D5E94C6CFF0496ACF43EAD9EF77E6B46137B98D

def egcd(a, b):
    if a == 0:
        return (b, 0, 1)
    else:
        g, y, x = egcd(b % a, a)
        return (g, x - (b // a) * y, y)

def modinv(a, m):
    g, x, y = egcd(a % m, m)
    if g != 1:
        return None
    else:
        return x % m

def legendre_symbol(a, p):
    """
    Legendre symbol
    Define if a is a quadratic residue modulo odd prime
    http://en.wikipedia.org/wiki/Legendre_symbol
    """
    ls = pow(a, (p - 1)//2, p)
    if ls == p - 1:
        return -1
    return ls

def modsqrt(a, p):
    """
    Square root modulo prime number
    Solve the equation
        x^2 = a mod p
    http://en.wikipedia.org/wiki/Tonelli-Shanks_algorithm
    """
    a %= p

    # Simple case
    if a == 0:
        return None
    if p == 2:
        return a

    # Check solution existence on odd prime
    if legendre_symbol(a, p) != 1:
        return None

    # Simple case
    if p % 4 == 3:
        x = pow(a, (p + 1)//4, p)
        return x

    # Factor p-1 on the form q * 2^s (with Q odd)
    q, s = p - 1, 0
    while q % 2 == 0:
        s += 1
        q //= 2

    # Select a z which is a quadratic non resudue modulo p
    z = 1
    while legendre_symbol(z, p) != -1:
        z += 1
    c = pow(z, q, p)

    # Search for a solution
    x = pow(a, (q + 1)//2, p)
    t = pow(a, q, p)
    m = s
    while t != 1:
        # Find the lowest i such that t^(2^i) = 1
        i, e = 0, 2
        for i in range(1, m):
            if pow(t, e, p) == 1:
                break
            e *= 2

        # Update next value to iterate
        b = pow(c, 2**(m - i - 1), p)
        x = (x * b) % p
        t = (t * b * b) % p
        c = (b * b) % p
        m = i

    return x

class EllipticCurve:
    def __init__(self, p, a, b, n):
        self.p = p
        self.a = a % p
        self.b = b % p
        self.n = n

    def order(self):
        return n

    def affine(self, p1):
        x1, y1, z1 = p1
        if z1 == 0:
            return None
        inv = modinv(z1, self.p)
        inv_2 = (inv**2) % self.p
        inv_3 = (inv_2 * inv) % self.p
        return ((inv_2 * x1) % self.p, (inv_3 * y1) % self.p, 1)

    def negate(self, p1):
        x1, y1, z1 = p1
        return (x1, (self.p - y1) % self.p, z1)

    def is_x_coord(self, x):
        x_3 = pow(x, 3, self.p)
        return legendre_symbol(x_3 + self.a * x + self.b, self.p) != -1

    def lift_x(self, x):
        x_3 = pow(x, 3, self.p)
        v = x_3 + self.a * x + self.b
        y = modsqrt(v, self.p)
        if y is None:
            return None
        return (x, y, 1)

    def double(self, p1):
        x1, y1, z1 = p1
        if z1 == 0:
            return (0, 1, 0)
        y1_2 = (y1**2) % self.p
        y1_4 = (y1_2**2) % self.p
        x1_2 = (x1**2) % self.p
        s = (4*x1*y1_2) % self.p
        m = 3*x1_2
        if self.a:
            m += self.a * pow(z1, 4, self.p)
        m = m % self.p
        x3 = (m**2 - 2*s) % self.p
        y3 = (m*(s - x3) - 8*y1_4) % self.p
        z3 = (2*y1*z1) % self.p
        return (x3, y3, z3)

    def add_mixed(self, p1, p2):
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        assert(z2 == 1)
        if z1 == 0:
            return p2
        z1_2 = (z1**2) % self.p
        z1_3 = (z1_2 * z1) % self.p
        u2 = (x2 * z1_2) % self.p
        s2 = (y2 * z1_3) % self.p
        if x1 == u2:
            if (y1 != s2):
                return (0, 1, 0)
            return self.double(p1)
        h = u2 - x1
        r = s2 - y1
        h_2 = (h**2) % self.p
        h_3 = (h_2 * h) % self.p
        u1_h_2 = (x1 * h_2) % self.p
        x3 = (r**2 - h_3 - 2*u1_h_2) % self.p
        y3 = (r*(u1_h_2 - x3) - y1*h_3) % self.p
        z3 = (h*z1*z2) % self.p
        return (x3, y3, z3)

    def add(self, p1, p2):
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        if z1 == 0:
            return p2
        if z2 == 0:
            return p1
        if z1 == 1:
            return self.add_mixed(p2, p1)
        if z2 == 1:
            return self.add_mixed(p1, p2)
        z1_2 = (z1**2) % self.p
        z1_3 = (z1_2 * z1) % self.p
        z2_2 = (z2**2) % self.p
        z2_3 = (z2_2 * z2) % self.p
        u1 = (x1 * z2_2) % self.p
        u2 = (x2 * z1_2) % self.p
        s1 = (y1 * z2_3) % self.p
        s2 = (y2 * z1_3) % self.p
        if u1 == u2:
            if (s1 != s2):
                return (0, 1, 0)
            return self.double(p1)
        h = u2 - u1
        r = s2 - s1
        h_2 = (h**2) % self.p
        h_3 = (h_2 * h) % self.p
        u1_h_2 = (u1 * h_2) % self.p
        x3 = (r**2 - h_3 - 2*u1_h_2) % self.p
        y3 = (r*(u1_h_2 - x3) - s1*h_3) % self.p
        z3 = (h*z1*z2) % self.p
        return (x3, y3, z3)

    def mul(self, p1, n):
        r = (0, 1, 0)
        for i in range(n.bit_length() - 1, -1, -1):
            r = self.double(r)
            if ((n >> i) & 1):
                r = self.add(r, p1)
        return r

class Expr:
    def __init__(self, v):
        if isinstance(v, int):
            self.const = (v % P)
            self.linear = []
        elif isinstance(v, str):
            self.const = 0
            self.linear = [(v, 1)]
        else:
            raise RuntimeError("Expr must be constructed with int or variable name")

    def __add__(self, o):
        if isinstance(o, int) or isinstance(o, str):
            o = Expr(o)
        ret = Expr(self.const + o.const)
        for (varname, factor) in sorted(self.linear + o.linear):
            if len(ret.linear) and ret.linear[-1][0] == varname:
                ret.linear[-1] = (varname, (ret.linear[-1][1] + factor) % P)
            else:
                ret.linear.append((varname, factor))
            if len(ret.linear) and ret.linear[-1][1] == 0:
                ret.linear.pop()
        return ret

    def __radd__(self, o):
        return self.__add__(o)

    def __mul__(self, v):
        if isinstance(v, int):
            if v == 0:
                return Expr(0)
            ret = Expr((self.const * v) % P)
            ret.linear = [(varname, (factor * v) % P) for (varname, factor) in self.linear]
            return ret
        else:
            raise RuntimeError("Expr can only be multiplied with an integer")

    def __rmul__(self, v):
        return self.__mul__(v)

    def __neg__(self):
        return self.__mul__(-1)

    def __sub__(self, o):
        return self.__add__(-o)

    def __rsub__(self, o):
        return self.__neg__().__add__(o)

    def __str__(self):
        terms = []
        if self.const != 0 or len(self.linear) == 0:
            terms.append(str(self.const))
        for (varname, factor) in self.linear:
            if (factor == 1):
                terms.append(varname)
            else:
                terms.append("%i * %s" % (factor, varname))
        if len(terms) == 1:
            return terms[0]
        else:
            return "(" + (" + ".join(terms)) + ")"

    def evaluate(self, m):
        if self.const is None:
            return None
        ret = self.const
        for (varname, factor) in self.linear:
            if varname in m and m[varname] is not None:
                ret += m[varname] * factor
            else:
                return None
        return ret % P

    # split in constant and non-constant part
    def split(self):
        e = Expr(0)
        e.linear = self.linear
        return (Expr(self.const), e)

class Transcript:
    def __init__(self):
        self.varmap = dict()
        self.muls = []
        self.mul_cache = dict()
        self.div_cache = dict()
        self.bool_cache = dict()
#        self.bits_cache = dict()
        self.eqs = []

    def secret(self, v):
        i = len(self.varmap)
        varname = "v[%i]" % i
        self.varmap[varname] = v
        return Expr(varname)

    def mul(self, e1, e2):
        se1, se2 = str(e1), str(e2)
        if (se1, se2) in self.mul_cache:
            return self.mul_cache[(se1, se2)]
        if (se2, se1) in self.mul_cache:
            return self.mul_cache[(se2, se1)]
        ve1, ve2 = e1.evaluate(self.varmap), e2.evaluate(self.varmap)
        val = (ve1 * ve2) % P if ve1 is not None and ve2 is not None else None
        ret = self.secret(val)
        self.mul_cache[(se1, se2)] = ret
        self.muls.append((e1, e2, ret))
        return ret

    def div(self, e1, e2):
        se1, se2 = str(e1), str(e2)
        if (se1, se2) in self.div_cache:
            return self.div_cache[(se1, se2)]
        ve1, ve2 = e1.evaluate(self.varmap), e2.evaluate(self.varmap)
        if ve2 is not None and ve2 == 0:
            raise RuntimeError("Division by zero")
        val = (ve1 * modinv(ve2, P)) % P if ve1 is not None and ve2 is not None else None
        ret = self.secret(val)
        self.div_cache[(se1, se2)] = ret
        self.muls.append((ret, e2, e1))
        return ret

    def boolean(self, e):
        se = str(e)
        if se in self.bool_cache:
            return e
        ve = e.evaluate(self.varmap)
        if ve is not None and ve != 0 and ve != 1:
            raise RuntimeError("Boolean constraint on non-boolean value")
        self.bool_cache[se] = True
        self.muls.append((e, e - 1, Expr(0)))
        return e

    def equal(self, e1, e2):
        eq = e1 - e2
        ve = eq.evaluate(self.varmap)
        if ve is not None and ve != 0:
            raise RuntimeError("Equation mismatch")
        self.eqs.append(e1 - e2)

    def evaluate(self, e):
        return e.evaluate(self.varmap)

#    def bits(self, e, n):
#        se = str(e)
#        if (se, n) in self.bits_cache:
#            return self.bits_cache[(se, n)]
#        ve = e.evaluate(self.varmap)
#        vals = [None for _ in range(n)]
#        if ve is not None:
#            if ve >= 2 ** n:
#                raise RuntimeError("Overflow in bits decomposition")
#            vals = [(ve >> i) & 1 for i in range(n)]
#        ret = [self.secret(vals[i]) for i in range(n)]
#        self.bits_cache[(se, n)] = ret
#        bitsum = sum(ret[i] * (1 << i) for i in range(n)]
#        self.eqs.append(bitsum - e)
#        return ret

# A transcript that can be turned into libsecp256k1-zkp circuit and assignment format
class BulletproofsTranscript:
    def __init__(self, transcript, n_bits):
        # Number of bit constraints. We don't need to explicitly state them for
        # bulletproofs.
        self.n_bits = n_bits
        # libsecp-zkp bulletproofs require power of 2 muls
        self.n_muls = 2**ceil(log(len(transcript.muls), 2))
        # Simple assignments of wires, for example (L0, v[0])
        self.assignments = []
        # Assignments of wires as linear combination of other wires, for example (L1, L0 + v[1])
        self.linear_assignments = []
        # Filled with n_bits many bit constraints.
        self.bit_constraints = []
        # Constraints we will encode
        self.constraints = []
        # Map from "v[i]" coming from the transcript to a bulletproofs variable name (i.e. "Li", "Ri", "Oi")
        self.vtoA = {}
        # There's a single commitment in purify
        self.n_commitments = 1

        for (i, (l, r, o)) in enumerate(transcript.muls):
            # Need to copy because the muls elements are the same expressions
            # sometimes, but we rely on being able to change the expressions
            # independently
            self.add_mul("L", i, copy.deepcopy(l))
            self.add_mul("R", i, copy.deepcopy(r))
            self.add_mul("O", i, copy.deepcopy(o))
        for i in range(len(transcript.muls), self.n_muls):
            self.add_mul("L", i, Expr(0))
            self.add_mul("R", i, Expr(0))
            self.add_mul("O", i, Expr(0))

    # Replaces "v[i]" in an expr with the corresponding "Li", "Ri", "Oi"
    def replace_expr_v_with_bp_var(self, e):
        e.linear = list(map(lambda x: x if not x[0] in self.vtoA else (self.vtoA[x[0]], x[1]), e.linear))

    # Returns whether expr is a simple assignment
    def replace_and_insert(self, expr, s):
        if len(expr.linear) >= 1:
            self.replace_expr_v_with_bp_var(expr)
            if expr.const == 0 and len(expr.linear) == 1 and not expr.linear[0][0] in self.vtoA:
                self.vtoA[expr.linear[0][0]] = s
                if "v[" in expr.linear[0][0]:
                    return True
        return False

    def add_mul(self, s, i, expr):
        varname = s + str(i)
        is_assignment = self.replace_and_insert(expr, varname)
        if is_assignment:
            self.assignments += [(varname, expr)]
        else:
            # Split the expression, because only the constant part must be on
            # the right hand side of the equation.
            c, l = expr.split()
            e = Expr(varname)
            lhs = e - l
            self.linear_assignments += [(varname, expr)]
            # Skip bit constraints
            if len(self.bit_constraints) < 2*self.n_bits:
                self.bit_constraints += [(lhs, c)]
            else:
                self.constraints += [(lhs, c)]

    def add_pubkey_and_out(self, pubkey, P1x, P2x, out):
        def a(pk, Px):
            self.replace_expr_v_with_bp_var(Px)
            c, l = Px.split()
            tup = (l, pk - c)
            self.constraints += [tup]
        a(pubkey % P, P1x)
        a(pubkey // P, P2x)
        self.replace_expr_v_with_bp_var(out)
        # Add constraint to for commitment
        self.constraints += [(out - Expr("V0"), Expr(0))]

    # Return circuit in bulletproofs module plaintext format
    def plaintext_circuit(self):
        ret = "%i,%i,%i,%i;" % (self.n_muls, self.n_commitments, self.n_bits, len(self.constraints))
        i = 0
        for cons in self.constraints:
            cons0 = str(cons[0])
            cons1 = str(cons[1])
            # Remove unnecessary parantheses from Expression string after
            # verifying they don't do anything
            assert(cons0.count("(") == 0 or (cons0.count("(") == 1 and cons0[0] == "(" and cons0[-1] == ")"))
            assert(cons1.count("(") == 0 or (cons1.count("(") == 1 and cons1[0] == "(" and cons1[-1] == ")"))
            cons0 = cons0.replace("(","").replace(")","")
            cons1 = cons1.replace("(","").replace(")","")
            ret += "%s = %s;" % (cons0, cons1)
        return ret

    def write_circuit(self, f):
        version = 1
        f.write(version.to_bytes(4, byteorder='little'))
        f.write(self.n_commitments.to_bytes(4, byteorder='little'))
        f.write(self.n_muls.to_bytes(8, byteorder='little'))
        f.write(self.n_bits.to_bytes(8, byteorder='little'))
        f.write(len(self.constraints).to_bytes(8, byteorder='little'))

        # Copied from libsecp
        def secp256k1_bulletproofs_encoding_width(n):
            if n < 0x100:
                return 1
            if n < 0x10000:
                return 2;
            if n < 0x100000000:
                return 4;
            return 8;
        row_width = secp256k1_bulletproofs_encoding_width(self.n_muls)
        row_size = 0
        # In these "matrices" every row corresponds to a wire (f.e. wl[0] is
        # L0). Every entry in the row is a tuple of the constraints index this
        # wire is added to, and the factor its multiplied with before that.
        wl = [[]] * self.n_muls
        wr = [[]] * self.n_muls
        wo = [[]] * self.n_muls
        wv = [[]] * self.n_commitments

        def add_entry(w, var, constraint_idx, factor):
            var_idx = int(var[1:])
            w[var_idx] = w[var_idx] + [(constraint_idx, factor)]

        for (i, (left, _)) in enumerate(self.constraints):
            for summand in left.linear:
                if "L" == summand[0][0]:
                  add_entry(wl, summand[0], i, summand[1])
                elif "R" == summand[0][0]:
                  add_entry(wr, summand[0], i, summand[1])
                elif "O" == summand[0][0]:
                  add_entry(wo, summand[0], i, summand[1])
                elif "V" == summand[0][0]:
                  add_entry(wv, summand[0], i, summand[1])

        for row in wl + wr + wo + wv:
            row_width = secp256k1_bulletproofs_encoding_width(self.n_muls);
            f.write(len(row).to_bytes(row_width, byteorder='little'))
            for entry in row:
                f.write(entry[0].to_bytes(row_width, byteorder='little'))
                f.write(b'\x20')
                f.write(entry[1].to_bytes(32, byteorder='little'))

        # Write constant part (right hand side)
        for (_, right) in self.constraints:
            f.write(b'\x20')
            f.write(right.const.to_bytes(32, byteorder='little'))

    def evaluate(self, m, commitment):
        m["V0"] = commitment
        for (v, A)  in self.vtoA.items():
            m[A] = m[v]
        for assign in self.assignments + self.linear_assignments:
            m[assign[0]] = assign[1].evaluate(m)
        for i in range(self.n_muls):
            if (m["L%i" %i] * m["R%i" % i]) % P != m["O%i" % i]:
                return False
        for con in self.constraints + self.bit_constraints:
            if con[0].evaluate(m) != con[1].evaluate(m):
                return False
        return True

    # m must have been called with self.evaluate
    def write_assignment(self, m, f):
        version = 1
        f.write(version.to_bytes(4, byteorder='little'))
        f.write(self.n_commitments.to_bytes(4, byteorder='little'))
        f.write(self.n_muls.to_bytes(8, byteorder='little'))
        def write(s):
            for i in range(self.n_muls):
                f.write(b'\x20')
                f.write(m["%s%s" % (s, i)].to_bytes(32, byteorder='little'))
        write("L")
        write("R")
        write("O")
        f.write(b'\x20')
        f.write(m["V0"].to_bytes(32, byteorder='little'))

def hmac_sha256(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()

def hkdf(length, ikm, salt=b"", info=b""):
    """Implement HKDF using HMAC-SHA256."""

    prk = hmac_sha256(salt if len(salt) > 0 else bytes([0]*hash_len), ikm)
    t = b""
    okm = b""
    for i in range(ceil(length / 32)):
        t = hmac_sha256(prk, t + info + bytes([1+i]))
        okm += t
    return okm[:length]

def hash_to_int(data, rang, info=b""):
    """Implement a uniform hash-to-int using HKDF."""
    bits = rang.bit_length()
    mask = 2 ** bits - 1
    for i in range(256):
        v = int.from_bytes(hkdf((bits + 7) // 8, data, bytes([i]), info), 'big') & mask
        if v < rang:
            return v

def hash_to_curve(data, curve):
    """Implement a uniform hash-to-curve using HKDF."""
    rang = 2 * curve.p
    for i in range(256):
        v = hash_to_int(data, rang, bytes([i]))
        if curve.is_x_coord(v // 2):
            p = curve.lift_x(v // 2)
            if v & 1:
                p = curve.negate(p)
            return p

E1 = EllipticCurve(P, A, B, N1)
E2 = EllipticCurve(P, (A * D * D) % P, (B * D * D * D) % P, N2)
G1 = hash_to_curve(b"Generator/1", E1)
G2 = hash_to_curve(b"Generator/2", E2)
assert(E1.mul(G1, N1)[2] == 0) # G1's order divides N1
assert(E2.mul(G2, N2)[2] == 0) # G2's order divides N2
assert(legendre_symbol(D, P) == -1)
DI = modinv(D, P)

def unpack_secret(z):
    """Convert a single integer in range 0..(N1-1)*(N2-1)/4-1 to a pair of scalars."""
    return (1 + (z % ((N1 - 1) // 2)), 1 + (z // ((N1 - 1) // 2)))

def unpack_public(p):
    """Convert a single integer in range 0..P^2-1 to a pair of coordinates."""
    return (p % P, p // P)

def pack_public(x1, x2):
    """Convert a pair of coordinates to a single integer in range 0..P^2-1."""
    return (x1 + P * x2)

def combine(x1, x2):
    """Combine two x coordinates into the PRF output."""
    u = x1 % P
    v = (x2 * DI) % P
    w = modinv(u - v + P, P)
    return (((u + v) * (A + u * v) + 2 * B) * w * w) % P

def key_to_bits(n, bits):
    """Convert the scalar n to a list of bits that encode it for use in the circuit."""
    n -= 1
    if n >= (1 << bits):
        raise RuntimeError("Key out of range")
    ret = [(n >> i) & 1 for i in range(bits)]
    for i in range(3, bits, 3):
        if not ret[i]:
            ret[i - 1] = 1 - ret[i - 1]
            ret[i - 2] = 1 - ret[i - 2]
        ret[i] = 1 - ret[i]
    return ret

def circuit_1bit(v, _trans, x):
    """Construct a circuit that looks up one of the v values based on boolean x."""
    return v[0] + x * (v[1] - v[0])

def circuit_2bit(v, trans, x, y):
    """Construct a circuit that looks up one of the v values based on booleans x and y."""
    xy = trans.mul(x, y)
    return v[0] + x * (v[1] - v[0]) + y * (v[2] - v[0]) + xy * (v[0] + v[3] - v[1] - v[2])

def circuit_3bit(v, trans, x, y, z):
    """Construct a circuit that looks up one of the v values based on booleans x, y, and z."""
    xy = trans.mul(x, y)
    yz = trans.mul(y, z)
    zx = trans.mul(z, x)
    xyz = trans.mul(xy, z)
    return v[0] + x * (v[1] - v[0]) + y * (v[2] - v[0]) + z * (v[4] - v[0]) + xy * (v[0] + v[3] - v[1] - v[2]) + zx * (v[0] + v[5] - v[1] - v[4]) + yz * (v[0] + v[6] - v[2] - v[4]) + xyz * (v[1] + v[2] + v[4] + v[7] - v[0] - v[3] - v[5] - v[6])

def circuit_1bit_point(curve, ps, trans, b0):
    """Construct a circuit that returns one of the 2 points in ps, based on boolean b0."""
    aps = [curve.affine(p) for p in ps]
    x_coord = circuit_1bit([aps[0][0], aps[1][0]], trans, b0)
    y_coord = circuit_1bit([aps[0][1], aps[1][1]], trans, b0)
    return (x_coord, y_coord)

def circuit_2bit_point(curve, ps, trans, b0, b1):
    """Construct a circuit that returns one of the 4 points in ps, based on booleans b0 and b1."""
    aps = [curve.affine(p) for p in ps]
    x_coord = circuit_2bit([aps[0][0], aps[1][0], aps[2][0], aps[3][0]], trans, b0, b1)
    y_coord = circuit_2bit([aps[0][1], aps[1][1], aps[2][1], aps[3][1]], trans, b0, b1)
    return (x_coord, y_coord)

def circuit_3bit_point(curve, ps, trans, b0, b1, b2):
    """Construct a circuit that returns one of the 8 points in ps, based on booleans b0, b1, and b2."""
    aps = [curve.affine(p) for p in ps]
    x_coord = circuit_3bit([aps[0][0], aps[1][0], aps[2][0], aps[3][0], aps[4][0], aps[5][0], aps[6][0], aps[7][0]], trans, b0, b1, b2)
    y_coord = circuit_3bit([aps[0][1], aps[1][1], aps[2][1], aps[3][1], aps[4][1], aps[5][1], aps[6][1], aps[7][1]], trans, b0, b1, b2)
    return (x_coord, y_coord)

def circuit_optionally_negate_ec(curve, p, trans, bn):
    """Construct a circuit that optionally negates a point, based on boolean bn."""
    return (p[0], trans.mul(1 - 2 * bn, p[1]))

def circuit_ec_add(curve, trans, p1, p2):
    """Construct a circuit that performs EC addition between two affine points (which are guaranteed by the caller to not be equal or each other's negation)."""
    lam = trans.div(p2[1] - p1[1], p2[0] - p1[0])
    x_coord = trans.mul(lam, lam) - p1[0] - p2[0]
    y_coord = trans.mul(lam, p1[0] - x_coord) - p1[1]
    return (x_coord, y_coord)

def circuit_ec_add_x(curve, trans, p1, p2):
    """Construct a circuit that computes the X coordinate of the addition between two affine points (which are guaranteed by the caller to not be equal or each other's negation)."""
    lam = trans.div(p2[1] - p1[1], p2[0] - p1[0])
    x_coord = trans.mul(lam, lam) - p1[0] - p2[0]
    return x_coord

def circuit_ec_multiply_x(curve, trans, p, bits):
    """Construct a circuit that computes the X coordinate of a point p times the scalar whose bit-decomposition (by key_to_bits) is bits."""
    # Compute powers of 2 multiplied by P
    p_pows = [p]
    for i in range(len(bits) - 1):
        p_pows.append(curve.double(p_pows[-1]))

    lookups = []
    for i in range((len(bits) - 1) // 3):
        p1 = p_pows[i * 3]
        p3 = curve.add(p1, p_pows[i * 3 + 1])
        p5 = curve.add(p3, p_pows[i * 3 + 1])
        p7 = curve.add(p5, p_pows[i * 3 + 1])
        lookups.append(circuit_optionally_negate_ec(curve, circuit_2bit_point(curve, [p1, p3, p5, p7], trans, bits[i * 3 + 1], bits[i * 3 + 2]), trans, bits[i * 3 + 3]))

    if len(bits) % 3 == 0:
        pn = p_pows[-3]
        p3n = curve.add(pn, p_pows[-2])
        p5n = curve.add(p3n, p_pows[-2])
        p7n = curve.add(p5n, p_pows[-2])
        pn1 = curve.add(pn, p_pows[0])
        p3n1 = curve.add(p3n, p_pows[0])
        p5n1 = curve.add(p5n, p_pows[0])
        p7n1 = curve.add(p7n, p_pows[0])
        lookups.append(circuit_3bit_point(curve, [pn, pn1, p3n, p3n1, p5n, p5n1, p7n, p7n1], trans, bits[0], bits[-2], bits[-1]))
    elif len(bits) % 3 == 1:
        pn = p_pows[-1]
        pn1 = curve.add(pn, p_pows[0])
        lookups.append(circuit_1bit_point(curve, [pn, pn1], trans, bits[0]))
    else:
        pn = p_pows[-2]
        p3n = curve.add(pn, p_pows[-1])
        pn1 = curve.add(pn, p_pows[0])
        p3n1 = curve.add(p3n, p_pows[0])
        lookups.append(circuit_2bit_point(curve, [pn, pn1, p3n, p3n1], trans, bits[0], bits[-1]))

    ret = lookups[0]
    for i in range(1, len(lookups) - 1):
        ret = circuit_ec_add(curve, trans, ret, lookups[i])
    return circuit_ec_add_x(curve, trans, ret, lookups[-1])

def circuit_combine(trans, x1, x2):
    """Construct a circuit that combines two uniform X values (on E1 and E2) into a uniform GF(P) element."""
    u = x1
    v = x2 * DI
    return trans.div(trans.mul(u + v, trans.mul(u, v) + A) + 2 * B, trans.mul(u - v, u -v))

def circuit_main(trans, M1, M2, z1=None, z2=None):
    z1bitvals = [None for _ in range(N1.bit_length() - 1)]
    z2bitvals = [None for _ in range(N2.bit_length() - 1)]
    if z1 is not None and z2 is not None:
        z1bitvals = key_to_bits(z1, N1.bit_length() - 1)
        z2bitvals = key_to_bits(z2, N2.bit_length() - 1)
    z1bits = [trans.boolean(trans.secret(z1bitval)) for z1bitval in z1bitvals]
    z2bits = [trans.boolean(trans.secret(z2bitval)) for z2bitval in z2bitvals]
    # number of bit constraints
    n_bits = len(z1bits) + len(z2bits)
    out_P1x = circuit_ec_multiply_x(E1, trans, G1, z1bits)
    out_P2x = circuit_ec_multiply_x(E2, trans, G2, z2bits)
    out_x1 = circuit_ec_multiply_x(E1, trans, M1, z1bits)
    out_x2 = circuit_ec_multiply_x(E2, trans, M2, z2bits)
    return (circuit_combine(trans, out_x1, out_x2), out_P1x, out_P2x, n_bits)

# verifier command with python output
def verifier_cmd_python(trans, P1x, P2x, out):
    print("def verify(pubkey, output, v):")
    print("    P = %i" % P)
    print("    # %i multiplications" % len(trans.muls))
    for (a, b, m) in trans.muls:
        print("    assert((%s * %s - %s) %% P == 0)" % (a, b, m))
    print("    # %i linear equations" % len(trans.eqs))
    for (eq) in trans.eqs:
        print("    assert((%s) %% P == 0)" % eq)
    print("    # Verify public key")
    print("    assert(%s %% P == pubkey %% P)" % P1x)
    print("    assert(%s %% P == pubkey // P)" % P2x)
    print("    # Verify output")
    print("    assert(output == %s %% P)" % out)

# verifier command with bulletproofs output
def verifier_cmd_bulletproofs(fname, trans, n_bits, pubkey, P1x, P2x, out):
    b_trans = BulletproofsTranscript(trans, n_bits)
    b_trans.add_pubkey_and_out(pubkey, P1x, P2x, out)
    with open(fname, 'wb') as f:
        b_trans.write_circuit(f)

# This function prints a python script that uses the Z3 theorem prover to solve
# the circuit. If Z3 would find a wire assignment, this circuit is broken. It
# would be possible to make a verifier accept a proof without having access to
# secret key (aka nonce key). Additionally, it may be possible to create proofs
# for different outputs given the same message and pubkeys.
def verifier_cmd_z3(trans, pubkey, P1x, P2x, out):
    len_v = len(trans.varmap)
    print("from z3 import *")
    print("s = Solver()")
    print("P = %i" % P)
    print("v = IntVector('v', %i)" % len_v)

    for i in range(len_v):
        print("s.add(v[%i] >= 0, v[%i] < P)" % (i, i))
    print("# %i multiplications" % len(trans.muls))
    for (a, b, m) in trans.muls:
        print("s.add((%s * %s - %s) %% P == 0)" % (a, b, m))
    print("# %i linear equations" % len(trans.eqs))
    for (eq) in trans.eqs:
         print("s.add((%s) %% P == 0)" % eq)
    print("# Verify public key")
    print("s.add(%s %% P == %s %% P)" % (P1x, pubkey))
    print("s.add(%s %% P == %s // P)" % (P2x, pubkey))
    print("print(\"Checking...\")")
    print("s.check()")
    print("model = s.model()")
    print("for var in model:")
    print("    print(var, model[var])")

# prove command with python output
def prove_cmd_python(trans, pubkey, out_native):
    print("verify(0x%x, 0x%x, [%s])" % (pubkey, out_native, ",".join("%s" % (trans.varmap["v[%i]" % i]) for i in range(len(trans.varmap)))))

# prove command with bulletproofs output
def prove_cmd_bulletproofs(fname, trans, n_bits, pubkey, P1x, P2x, out, out_native):
    b_trans = BulletproofsTranscript(trans, n_bits)
    b_trans.add_pubkey_and_out(pubkey, P1x, P2x, out)
    assert(b_trans.evaluate(trans.varmap, out_native))
    with open(fname, 'wb') as f:
        b_trans.write_assignment(trans.varmap, f)

arg_parser = argparse.ArgumentParser(description='A PRF with low multiplicative complexity', usage='''%s <command> [<args>]
    The available commands are:
    %s gen [--seckey <seckey>]: generate a key
    %s eval <hexmsg> <seckey>: evaluate the PRF
    %s verifier <hexmsg> <pubkey> [--z3 | --bulletproofs-outfile <file>]: output verifier circuit for a given message
    %s prove <hexmsg> <seckey> [--bulletproofs-outfile <file>]: produce input for verifier
    ''' % ((__file__,)*5))
arg_parser.add_argument('cmd', choices=['gen', 'eval', 'verifier', 'prove'])
args = arg_parser.parse_args(sys.argv[1:2])

if args.cmd == "gen":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--seckey', required=False)
    args = arg_parser.parse_args(sys.argv[2:])
    if args.seckey is None:
        z = secrets.randbelow((N1 - 1) // 2 * (N2 - 1) // 2)
    else:
        z = int(args.seckey, 16)
    z1, z2 = unpack_secret(z)
    P1 = E1.affine(E1.mul(G1, z1))
    P2 = E2.affine(E2.mul(G2, z2))

    print("z=%x # private key" % z)
    print("x=%x # public key" % pack_public(P1[0], P2[0]))
elif args.cmd == "eval":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('hexmsg')
    arg_parser.add_argument('seckey')
    args = arg_parser.parse_args(sys.argv[2:])

    z = int(args.seckey, 16)
    m = bytes.fromhex(args.hexmsg)
    z1, z2 = unpack_secret(z)
    M1 = hash_to_curve(b"Eval/1/" + m, E1)
    M2 = hash_to_curve(b"Eval/2/" + m, E2)
    Q1 = E1.affine(E1.mul(M1, z1))
    Q2 = E2.affine(E2.mul(M2, z2))
    out = combine(Q1[0], Q2[0])
    print("eval: %x" % out)
elif args.cmd == "verifier":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('hexmsg')
    arg_parser.add_argument('pubkey')
    group = arg_parser.add_mutually_exclusive_group()
    group.add_argument('-b', '--bulletproofs-outfile')
    group.add_argument('-z', '--z3', action="store_true")

    args = arg_parser.parse_args(sys.argv[2:])

    m = bytes.fromhex(args.hexmsg)
    pubkey = int(args.pubkey, 16)
    M1 = hash_to_curve(b"Eval/1/" + m, E1)
    M2 = hash_to_curve(b"Eval/2/" + m, E2)
    trans = Transcript()
    out, P1x, P2x, n_bits = circuit_main(trans, M1, M2)

    if args.bulletproofs_outfile is None and args.z3 is False:
        verifier_cmd_python(trans, P1x, P2x, out)
    elif args.z3 is True:
        verifier_cmd_z3(trans, pubkey, P1x, P2x, out)
    else:
        verifier_cmd_bulletproofs(args.bulletproofs_outfile, trans, n_bits, pubkey, P1x, P2x, out)

elif args.cmd == "prove":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('hexmsg')
    arg_parser.add_argument('seckey')
    arg_parser.add_argument('--bulletproofs-outfile')
    args = arg_parser.parse_args(sys.argv[2:])

    m = bytes.fromhex(args.hexmsg)
    z = int(args.seckey, 16)
    z1, z2 = unpack_secret(z)
    M1 = hash_to_curve(b"Eval/1/" + m, E1)
    M2 = hash_to_curve(b"Eval/2/" + m, E2)
    P1 = E1.affine(E1.mul(G1, z1))
    P2 = E2.affine(E2.mul(G2, z2))
    Q1 = E1.affine(E1.mul(M1, z1))
    Q2 = E2.affine(E2.mul(M2, z2))
    out_native = combine(Q1[0], Q2[0])
    trans = Transcript()
    out, P1x, P2x, n_bits = circuit_main(trans, M1, M2, z1, z2)
    assert(trans.evaluate(P1x) == P1[0])
    assert(trans.evaluate(P2x) == P2[0])
    assert(trans.evaluate(out) == out_native)
    pubkey = pack_public(P1[0], P2[0])

    if args.bulletproofs_outfile is None:
        prove_cmd_python(trans, pubkey, out_native)
    else:
        prove_cmd_bulletproofs(args.bulletproofs_outfile, trans, n_bits, pubkey, P1x, P2x, out, out_native)

else:
    print("Unknown command")
