import sys

if len(sys.argv) != 2:
    print("Usage: sage %s FIELD_SIZE" % __file__)
    sys.exit()

N = int(sys.argv[1])


if not is_prime(N):
    print("Field size is not prime: %i" % N)
    sys.exit()

F = GF(N)

# Find a non-square D in F
for D in range(1, 1000000):
    if not F(D).is_square():
        break
D = F(D)
D2 = D * D
D3 = D * D * D

def embedding_degree(Curve):
    size = Curve.coordinate_ring().base_ring().order()
    order = Curve.order()
    Fg = GF(order)
    x = Fg(size)
    # due to Fermat's little theorem
    for degree in divisors(order-1):
        if (x**degree == Fg(1)):
            return degree
    return -1

def embedding_degree_pretty_print(Curve, order_str):
    order = Curve.order()
    return "(%s - 1) / %i" % (order_str, (order-1)//embedding_degree(Curve))

sum_a_b = 1
iter = 0
while True:
    print("Iteration %i..." % iter)
    for a_val in range(0, sum_a_b):
        iter += 1
        a = F(a_val)
        b = F(sum_a_b - a_val)

        # Sanity check for non-singular curve
        if (4 * a * a * a + 27 * b * b) == 0:
            continue

        # Preliminary analysis on E1: y^2 = x^3 + a*x + b
        E1 = EllipticCurve(F, [a, b])
        n1 = E1.order()
        if not is_pseudoprime(n1):
            continue

        # Preliminary analysis on E2: y^2 = x^3 + a*x + b
        n2 = 2 * (N + 1) - n1
        if not is_pseudoprime(n2):
            continue
        E2 = EllipticCurve(F, [a*D*D, b*D*D*D])

        # Full primarily test on both
        if not is_prime(n1) or not is_prime(n2):
            continue

        print("P = %i # Field size" % N)
        print("A = %i # curve equation parameter A" % a)
        print("B = %i # curve equation parameter B" % b)
        print("D = %i # non-square in GF(P)" % D)
        print("N1 = %i # Order of E1: y^2 = x^3 + A*x + B over GF(P)" % n1)
        print("N2 = %i # Order of E2: y^2 = x^3 + A*D^2*x + B*D^3 over GF(P)" % n2)
        print("# ED1 = %s # Embedding degree of E1" % embedding_degree_pretty_print(E1, "N1"))
        print("# ED2 = %s # Embedding degree of E2" % embedding_degree_pretty_print(E2, "N2"))
        sys.exit()
    sum_a_b += 1

