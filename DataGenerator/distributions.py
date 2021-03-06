import itertools

import numpy as np
import scipy.stats


from Algorithms.Approximators.doctor_approximator import DoctorApproximator
from DataGenerator.data_generator import split_patients
from Database.antibioticsdatabase import AntibioticsDatabase


class Distribution:
    def __init__(self, seed=None):
        self.random = np.random.RandomState()
        self.random.seed(seed)

    def draw_z(self):
        pass
        # Return a representation of Z, this can be any format

    def draw_x(self, z):
        pass
        # Return a list of X values

    def draw_a(self, h, x, z):
        pass
        # Return a single integer representing the index of a treatment A

    def draw_y(self, a, h, x, z):
        pass
        # Return a tuple, (int, bool), representing the outcome of treatment a and if this is the last treatment that
        # should be tried

class ToyExampleDistribution(Distribution):
    def __init__(self):
        super().__init__()
        self.name = 'ToyExample'
    n_a = 3
    treatment_weights = np.array([0.65, 0.6, 0.4])
    results_array = np.array([[1, 0, 1, 0],
                              [1, 0, 0, 1],
                              [0, 1, 1, 0]])
    z_weights = np.array([0.45, 0.20, 0.20, 0.15])

    def draw_z(self):
        return self.random.choice(4, p=self.z_weights)

    def draw_x(self, z):
        return [0]

    def draw_a(self, h, x, z):
        weights = np.sum(self.z_weights * self.results_array, 1)
        if len(h) > 0:
            treatment_found = np.max(h, 0)[1]
            used_a = [u[0] for u in h]
            if treatment_found:
                weights = np.array([1, 1, 1])
                for u in used_a:
                    weights[u] = 0
            else:
                a_weights = self.results_array.copy()
                for u in used_a:
                    a_weights = a_weights - a_weights[u]
                    a_weights = np.maximum(a_weights, 0)
                a_weights = self.z_weights * a_weights
                weights = np.sum(a_weights, 1)

        return self.random.choice(3, p=weights/sum(weights))

    def draw_y(self, a, h, x, z):
        result = self.results_array[a][z]
        if len(h) > 0:
            best_result = np.max(h, 0)[1]
            if max(result, best_result) == 1 and self.random.random() < 0.85:
                return result, True
        return result, False

# Creates a random distribution with binary discrete covariates and moderators
class DiscreteDistribution(Distribution):
    def __init__(self, n_z, n_x, n_a, steps_y, outcome_sensitivity_x_z=1, seed=None):
        Distribution.__init__(self, seed)
        self.name = 'Discrete'
        self.n_z = n_z
        self.n_x = n_x
        self.n_a = n_a
        self.n_y = steps_y
        self.x_weight = outcome_sensitivity_x_z

        self.Pz = np.array(self.random.random(self.n_z))
        self.Px = np.array(self.random.random((self.n_x, self.n_z)))
        self.Px = (self.Px.T / np.sum(self.Px, 1)).T
        self.Pa = np.array(self.random.normal(0, 1, (1 + self.n_x + self.n_a, self.n_a)))
        self.Py = np.array(self.random.normal(0, 1, (self.n_a, 1 + self.n_x + self.n_z, self.n_y)))
        for coeffs in self.Py:
            coeffs[1:self.n_x+1] *= self.x_weight

    # Draw each Z_i according to the probabilities in Pz
    def draw_z(self):
        z = self.random.binomial(1, p=self.Pz)
        return z

    def calc_x_weights(self, z):
        weights_z = self.Px * z
        weights_x = np.maximum(np.minimum(np.sum(weights_z, 1), 0.98), 0.02)
        return weights_x

    def draw_x(self, z):
        x = self.random.binomial(1, p=self.calc_x_weights(z))
        return x.astype(int)

    def draw_a(self, h, x, z):
        tried_a = np.zeros(self.n_a)
        probs = np.zeros(self.n_a)
        for treatment in h:
            tried_a[treatment[0]] = treatment[1]
        v = np.concatenate(([1], x, tried_a))
        for i in range(self.n_a):
            probs[i] = np.exp(self.Pa.T.dot(v))[i]
        # Decrease the likelihood of testing "similar" treatments,
        # defined as the L2 norm of their x-dependant feature vector
        for treatment in h:
            for a in range(self.n_a):
                probs[a] *= self.calc_a_closeness(treatment[0], a, x)
        den = np.sum(probs)
        probs = probs / den
        return self.random.choice(self.n_a, p=probs)

    def evaluate(self, subject):
        z, x, y_fac = subject
        mask_unknown_actions = y_fac.copy().astype(float)
        mask_unknown_actions[mask_unknown_actions != -1] = 0
        mask_unknown_actions[mask_unknown_actions == -1] = -np.inf
        mask_unknown_actions = np.append(mask_unknown_actions, 0)
        history = []
        action = self.draw_a(history, x, None)

        while action != self.n_a and len(history) < self.n_a:
            outcome = y_fac[action]
            history.append([action, outcome])
            if outcome >= self.n_y - 1 or len(history) >= self.n_a:
                break
            action = self.draw_a(history, x, None)
        return history

    def calc_a_closeness(self, a0, a1, x):
        cc = np.exp(self.Py[a0][0:self.n_x+1].T.dot(np.concatenate(([1], x)))) / sum(np.exp(self.Py[a0][0:self.n_x+1].T.dot(np.concatenate(([1], x)))))
        dd = np.exp(self.Py[a1][0:self.n_x+1].T.dot(np.concatenate(([1], x)))) / sum(np.exp(self.Py[a1][0:self.n_x+1].T.dot(np.concatenate(([1], x)))))
        return np.linalg.norm(cc - dd)

    def calc_y_weights(self, a, x, z):
        v = np.concatenate(([1], x, z))
        probs = np.zeros(self.n_y)
        for i in range(self.n_y):
            probs[i] = np.exp(self.Py[a].T.dot(v)).T[i]
        den = np.sum(probs)
        probs = probs / den
        return probs

    def draw_y(self, a, h, x, z):
        probs = self.calc_y_weights(a, x, z)
        y = self.random.choice(self.n_y, p=probs)
        done = False
        if (y >= self.n_y - 1 and self.random.random() < 0.9) or self.random.random() < 0.1:
            done = True
        return y, done

    def get_z_probability(self, z):
        pz = 1
        for i in range(self.n_z):
            pz *= self.Pz[i] ** z[i] * (1 - self.Pz[i]) ** (1 - z[i])
        return pz

    def calc_x_given_z_probability(self, z, x):
        x_weights = self.calc_x_weights(z)
        px = 1
        for i in range(self.n_x):
            px *= x_weights[i] ** x[i] * (1 - x_weights[i]) ** (1 - x[i])
        return px

    def calc_x_probability(self, x):
        px = 0
        for z in itertools.product(range(2), repeat=self.n_z):
            px += self.calc_x_given_z_probability(z, x) * self.get_z_probability(z)
        return px

    def calc_z_given_x_probability(self, z, x):
        pz = self.get_z_probability(z)
        px = self.calc_x_probability(x)
        pxz = self.calc_x_given_z_probability(z, x)
        return pxz * pz / px

    def print_moderator_statistics(self):
        print("Probabilities for Z:")
        total = 0
        for z in itertools.product(range(2), repeat=self.n_z):
            pz = self.get_z_probability(z)
            print("{} : {:05.3f}".format(z, pz))
            total += pz
        assert np.isclose(total, 1, atol=0.000001), "Probabilities of moderators don't add up to 1. Something is wrong!"
        print("---------------------")

    def print_covariate_statistics(self):
        print("Probabilities for X:")
        total = 0
        for x in itertools.product(range(2), repeat=self.n_x):
            tot_px = self.calc_x_probability(x)
            total += tot_px
            print("{} : {:05.3f}".format(x, tot_px))

        assert np.isclose(total, 1, atol=0.000001), "Probabilities of covariates don't add up to 1. Something is wrong!"
        print("---------------------")

    def print_treatment_statistics(self):
        for a in range(self.n_a):
            print("Outcome probabilities for treatment A{}".format(a))
            print("{:{width}}".format('', width=self.n_x*3 + int(self.n_x == 1)), end='')
            for i in range(self.n_y):
                print("|{:^5}".format("Y=" + str(i)), end='')
            print("|")
            for x in itertools.product(range(2), repeat=self.n_x):
                tot_py = np.zeros(self.n_y)
                for z in itertools.product(range(2), repeat=self.n_z):
                    py = np.copy(self.calc_y_weights(a, x, z))
                    assert np.isclose(np.sum(py), 1, atol=0.000001), \
                        "Probabilities of treatment {} don't add up to 1 for x: {}, z: {}, is {}".format(a, x, z, np.sum(py))
                    py *= self.calc_z_given_x_probability(z, x)
                    tot_py += py
                print("{:{width}}".format(str(x), width=self.n_x*3 + int(self.n_x == 1)), end='')
                for i in range(self.n_y):
                    print("|{:05.3f}".format(tot_py[i]), end='')
                print("|")
            print("---------------------")

    def print_detailed_treatment_statistics(self):
        for a in range(self.n_a):
            print("Outcome probabilities for treatment A{}".format(a))
            print("{:{width}}".format('', width=self.n_x*3 + int(self.n_x == 1) + 1 + self.n_z*3), end='')
            for i in range(self.n_y):
                print("|{:^5}".format("Y=" + str(i)), end='')
            print("|")
            for x in itertools.product(range(2), repeat=self.n_x):
                print("{:{width}}".format(str(x), width=self.n_x*3), end=' ')
                for z in itertools.product(range(2), repeat=self.n_z):
                    print("{:{width}}".format(str(z), width=self.n_z * 3), end='')
                    py = np.copy(self.calc_y_weights(a, x, z))
                    assert np.isclose(np.sum(py), 1, atol=0.000001), \
                        "Probabilities of treatment {} don't add up to 1 for x: {}, z: {}, is {}".format(a, x, z,
                                                                                                         np.sum(py))
                    for i in range(self.n_y):
                        print("|{:05.3f}".format(py[i]), end='')
                    print("|")
                    if np.min(z) == 0:
                        print("{:{width}}".format("", width=self.n_x * 3 + int(self.n_x == 1) + 1), end='')
            print("---------------------")

class DiscreteDistributionWithStaticOutcomes(DiscreteDistribution):
    def __init__(self, n_z, n_x, n_a, steps_y, outcome_sensitivity_x_z=1, seed=None):
        super().__init__(n_z, n_x, n_a, steps_y, outcome_sensitivity_x_z, seed)
        self.name = "Discrete with static outcomes"

    def draw_y(self, a, h, x, z):
        probs = self.calc_y_weights(a, x, z)
        y = np.argmax(probs)
        done = False
        if y >= self.n_y - 1 and self.random.random() < 0.9:
            done = True
        return y, done


class DiscreteDistributionWithSmoothOutcomes(DiscreteDistribution):
    def __init__(self, n_z, n_x, n_a, steps_y, outcome_sensitivity_x_z=1, seed=None):
        super().__init__(n_z, n_x, n_a, steps_y, outcome_sensitivity_x_z, seed)
        self.name = "Discrete_with_smooth_outcomes"

        self.dists = dict()

        self.Py1 = np.array(self.random.normal(0, 1, (self.n_a, 1 + self.n_x + self.n_z)))
        self.Py2 = np.array(self.random.normal(0, 1, (self.n_a, 1 + self.n_x + self.n_z)))
        self.Py2[:, 0] = np.abs(self.Py2[:, 0])
        for coeffs in self.Py1:
            coeffs[1:self.n_x+1] *= self.x_weight
        for coeffs in self.Py2:
            coeffs[1:self.n_x+1] *= self.x_weight
        self.neg_Py1 = ((self.Py1 < 0)*self.Py1).sum(1)
        self.pos_Py1 = ((self.Py1 > 0)*self.Py1).sum(1)
        self.neg_Py2 = ((self.Py2 < 0)*self.Py2).sum(1)
        self.pos_Py2 = ((self.Py2 > 0)*self.Py2).sum(1)

    def calc_a_closeness(self, a0, a1, x):
        d1 = self.Py1[a0] - self.Py1[a1]
        d2 = self.Py2[a0] - self.Py2[a1]

        return np.sum(d1**2) + np.sum(d2**2)

    def calc_y_weights(self, a, x, z):
        v = np.concatenate(([1], x, z))
        dist_index = tuple(np.concatenate(([a], x, z)))
        y0 = self.Py1[a].dot(v)
        y0 = (self.n_y - 1) * (y0 - self.neg_Py1[a]) / (self.pos_Py1[a] - self.neg_Py1[a])
        gamma = self.Py2[a].dot(v)
        gamma = (gamma - self.neg_Py2[a]) / (self.pos_Py2[a] - self.neg_Py2[a])
        probs = np.zeros(self.n_y)
        if dist_index in self.dists:
            dist = self.dists[dist_index]
        else:
            dist = scipy.stats.cauchy(y0, gamma)
            self.dists[dist_index] = dist
        for i in range(self.n_y):
            probs[i] = dist.pdf(i)
        probs = probs / sum(probs)
        return probs

class DiscreteDistributionWithInformation(DiscreteDistribution):
    def __init__(self, n_z, n_x, n_a, n_y, seed=None):
        super().__init__(n_z, n_x, n_a, n_y, seed=seed)
        self.name = "Discrete_with_information"

        self.Pz = np.array((0.5,)*self.n_z)
        self.y_coefficients = np.array(self.random.uniform(-1, 1, (self.n_a, 1 + self.n_x + self.n_z)))
        self.y_coefficients[:, 1:1+n_z] *= 5000

        self.outcome_probabilities = np.zeros((2,)*self.n_z + (2,)*self.n_x + (n_a,) + (n_y,))

        mean_outcomes = np.zeros((2,)*self.n_z + (2,)*self.n_x + (n_a,))
        for z, _ in np.ndenumerate(np.zeros((2,)*self.n_z)):
            for x, _ in np.ndenumerate(np.zeros((2,)*self.n_x)):
                for a in range(self.n_a):
                    coeffs = self.y_coefficients[a]
                    mean_outcomes[z+x+(a,)] = np.dot(coeffs, np.array((1,) + z + x))
        mean_outcomes += np.abs(np.min(mean_outcomes))
        mean_outcomes /= np.max(mean_outcomes)
        mean_outcomes *= (self.n_y - 0.7)
        for z, _ in np.ndenumerate(np.zeros((2,)*self.n_z)):
            for x, _ in np.ndenumerate(np.zeros((2,)*self.n_x)):
                for a in range(self.n_a):
                    dist = scipy.stats.cauchy(mean_outcomes[z+x+(a,)], self.random.uniform(0.2, 0.6))
                    for y in range(self.n_y):
                        self.outcome_probabilities[z+x+(a,)+(y,)] = dist.pdf(y)
                    self.outcome_probabilities[z+x+(a,)] /= np.sum(self.outcome_probabilities[z+x+(a,)])
                    assert np.isclose(np.sum(self.outcome_probabilities[z+x+(a,)]), 1, 0.00001), "z{}, x{}, a{}, sum{}".format(z, x, a, np.sum(self.outcome_probabilities[z+x+(a,)]))
        '''
        for z, _ in np.ndenumerate(np.zeros((2,)*self.n_z)):
            if self.random.random() < 1:
                x = tuple(np.random.binomial(1, 0.5, size=n_x))
                a0 = self.random.choice(self.n_a)
                a1 = self.random.choice(self.n_a)
                if a0 != a1:
                    for y in range(self.n_y):
                        self.outcome_probabilities[z+x+(a0,)+(y,)] = self.outcome_probabilities[z+x+(a1,)+(-(y+1),)]
                    print("Mirrored treatments {} and {} for x: {}, z: {}".format(a0, a1, x, z))
        '''
        # Reverse a treatment
        x = tuple(self.random.binomial(1, 0.5, size=self.n_x))
        for z, _ in np.ndenumerate(np.zeros((2,)*self.n_z)):
            a0 = 0
            a1 = self.n_a - 1
            for y in range(self.n_y):
                self.outcome_probabilities[z+x+(a0,)+(y,)] = self.outcome_probabilities[z+x+(a1,)+(-(y+1),)]

    def calc_a_closeness(self, a0, a1, x):
        return np.sum((self.y_coefficients[a0] - self.y_coefficients[a1]))**2

    def calc_y_weights(self, a, x, z):
        dist_index = tuple(np.concatenate((z, x, [a])))
        return self.outcome_probabilities[dist_index]


class ToyDistribution2(Distribution):
    def __init__(self, seed=None):
        super().__init__(seed)
        self.name = 'New'
    n_x = 1
    n_z = 3
    n_a = 3
    n_y = 3
    pz = np.array([0.3, 0.16, 0.35, 0.13, 0.04, 0.01, 0.01, 0.0])
    results_array = np.array([[2, 2, 1, 1, 1, 1, 0, 0],
                              [2, 1, 0, 2, 1, 1, 2, 0],
                              [1, 0, 2, 0, 1, 2, 0, 0]])

    def draw_z(self):
        return self.random.choice(8, p=self.pz)

    def draw_x(self, z):
        return [0]

    def draw_a(self, h, x, z):
        ev = np.sum(self.pz * (self.results_array == 2), 1)
        if len(h) > 0:
            used_a = [u[0] for u in h]
            for u in used_a:
                ev[u] = 0

        return self.random.choice(3, p=ev/sum(ev))

    def draw_y(self, a, h, x, z):
        y = self.results_array[a][z]
        max_y = 0
        if len(h) > 0:
            max_y = np.max(h, 0)[1]
        if ((max_y == 2 or y == 2) and self.random.random() < 0.90) or self.random.random() < 0.1:
            return y, True
        return y, False

    def calc_x_weights(self, z):
        return np.array([1, 0])

    def convert_binary_to_decimal(self, t):
        if t is int:
            return t
        t_val = 0
        for i in range(len(t)):
            t_val += 2**i*t[-(i+1)]
        return t_val

    def get_z_probability(self, z):
        z_val = self.convert_binary_to_decimal(z)
        return self.pz[z_val]

    def calc_y_weights(self, a, x, z):
        z_val = self.convert_binary_to_decimal(z)
        result = self.results_array[a][z_val]
        probs = np.zeros(3)
        probs[result] = 1
        return probs


class ToyDistribution2SlightlyRandom(ToyDistribution2):
    def draw_y(self, a, h, x, z):
        y = self.results_array[a][z]
        if self.random.random() < 0.15:
            y = self.random.choice(3)
        max_y = 0
        if len(h) > 0:
            max_y = np.max(h, 0)[1]
        if ((max_y == 2 or y == 2) and self.random.random() < 0.90) or self.random.random() < 0.1:
            return y, True
        return y, False

    def calc_y_weights(self, a, x, z):
        z_val = self.convert_binary_to_decimal(z)
        result = self.results_array[a][z_val]
        probs = np.ones(3)*0.05
        probs[result] = 0.9
        return probs


class SimulatedAntibiotics(Distribution):
    def __init__(self, seed=None):
        super().__init__(seed=seed)
        dist = AntibioticsDatabase(n_x=6, antibiotic_limit=50, seed=seed)
        training_data, test_data = dist.get_data()
        data = split_patients(training_data)
        n_x = dist.n_x
        n_a = dist.n_a
        n_y = dist.n_y
        self.doctor_approximator = DoctorApproximator(n_x, n_a, n_y, data)
        self.statistics = self.doctor_approximator.get_patient_statistics()

    def draw_x(self, z):
        pass

    def draw_a(self, h, x, z):
        pass

    def draw_z(self):
        pass
