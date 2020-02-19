import numpy as np
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import Axes3D


class Distribution:

    def __init__(self, seed=None):
        self.random = np.random.RandomState()
        self.random.seed(seed)

    def draw_z(self):
        return False

    def draw_x(self, z):
        return False

    def draw_a(self, h, x, z):
        return False

    def draw_y(self, a, h, x, z):
        return False


class TestDistribution(Distribution):
    n_treatments = 3

    def __init__(self):
        super().__init__()

    def draw_z(self):
        return self.random.randint(0, 3)

    def draw_x(self, z):
        x0 = max(0, 2 ** z - self.random.randint(-1, 2))
        x1 = self.random.randint(0, 2)
        return [x0, x1]

    def draw_a(self, h, x, z):
        possible_a = range(0, 3)
        if len(h) > 0:
            used_a = [x[0] for x in h]
        else:
            used_a = []
        draw_a = [x for x in possible_a if x not in used_a]
        self.random.shuffle(draw_a)
        return draw_a[0]

    def draw_y(self, a, h, x, z):
        assert 0 <= a < self.n_treatments
        y = 0
        if a == 0:
            y = self.random.normal(z)
        elif a == 1:
            y = self.random.uniform() * x[1]
        elif a == 2:
            y = self.random.normal(z - 1)
        return y


class SimpleDistribution(Distribution):
    n_treatments = 4
    Pzx = np.array([[0.5, 0.35, 0.15], [0.45, 0.25, 0.3]])
    Px = np.array([1 / 3, 2 / 3])
    Pz = np.array([0.467, 0.283, 0.25])

    Pxz = (Pzx.T * Px)
    Pxz = Pxz.T / Pz

    def draw_z(self):
        return int(self.random.choice([0, 1, 2], p=self.Pz))

    def draw_x(self, z):
        return self.random.choice(2, p=self.Pxz.T[z]/sum(self.Pxz.T[z]))

    def draw_a(self, h, x, z):
        possible_a = range(0, 4)
        if len(h) > 0:
            used_a = [x[0] for x in h]
        else:
            used_a = []
        draw_a = [x for x in possible_a if x not in used_a]
        self.random.shuffle(draw_a)
        return draw_a[0]

    def draw_y(self, a, h, x, z):
        ys = [[[0, 0], [0, 1], [1, 2]],
              [[0, 0], [2, 2], [0, 0]],
              [[2, 2], [1, 0], [0, 0]],
              [[1, 1], [1, 1], [1, 1]]]
        return ys[a][z][x]


class SkewedDistribution(SimpleDistribution):

    def __init__(self):
        super().__init__()

    def draw_a(self, h, x, z):
        possible_a = list(range(0, 4))
        if len(h) > 0:
            used_a = [x[0] for x in h]
        else:
            used_a = []
        possible_a = [a for a in possible_a if a not in used_a]
        if z == 2 and 3 not in used_a:
            return 3
        else:
            self.random.shuffle(possible_a)
            return possible_a[0]