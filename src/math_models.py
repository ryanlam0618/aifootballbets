import math
import numpy as np
from scipy.stats import poisson

class EloSystem:
    def __init__(self, k_factor=20, base_rating=1500):
        self.k = k_factor
        self.base = base_rating
        self.ratings = {} 

    def get_rating(self, team):
        return self.ratings.get(team, self.base)

    def expected_score(self, rating_a, rating_b):
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def update_ratings(self, home, away, h_goals, a_goals):
        if h_goals > a_goals:
            result_h, result_a = 1, 0
        elif h_goals == a_goals:
            result_h, result_a = 0.5, 0.5
        else:
            result_h, result_a = 0, 1

        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        
        expected_h = self.expected_score(r_h, r_a)
        expected_a = self.expected_score(r_a, r_h)
        
        self.ratings[home] = r_h + self.k * (result_h - expected_h)
        self.ratings[away] = r_a + self.k * (result_a - expected_a)

class PoissonModel:
    def __init__(self, home_expect, away_expect):
        self.mu_h = home_expect
        self.mu_a = away_expect

    def calculate_probabilities(self):
        prob_home, prob_draw, prob_away = 0, 0, 0
        for h in range(10):
            for a in range(10):
                p = poisson.pmf(h, self.mu_h) * poisson.pmf(a, self.mu_a)
                if h > a: prob_home += p
                elif h == a: prob_draw += p
                else: prob_away += p
        return {"ps_home": prob_home, "ps_draw": prob_draw, "ps_away": prob_away}

class DixonColesModel:
    def __init__(self, home_expect, away_expect, rho=-0.13):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.rho = rho

    def tau_correction(self, x, y):
        if x == 0 and y == 0: return 1 - (self.mu_h * self.mu_a * self.rho)
        elif x == 0 and y == 1: return 1 + (self.mu_h * self.rho)
        elif x == 1 and y == 0: return 1 + (self.mu_a * self.rho)
        elif x == 1 and y == 1: return 1 - (self.rho)
        else: return 1.0

    def calculate_probabilities(self):
        prob_home, prob_draw, prob_away = 0, 0, 0
        for h in range(10):
            for a in range(10):
                base = poisson.pmf(h, self.mu_h) * poisson.pmf(a, self.mu_a)
                correction = self.tau_correction(h, a)
                final = base * correction
                if h > a: prob_home += final
                elif h == a: prob_draw += final
                else: prob_away += final
        
        total = prob_home + prob_draw + prob_away
        return {"dc_home": prob_home/total, "dc_draw": prob_draw/total, "dc_away": prob_away/total}

class MonteCarloSimulator:
    def __init__(self, home_expect, away_expect, iterations=10000):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.iterations = iterations

    def run_simulation(self):
        h_goals = np.random.poisson(self.mu_h, self.iterations)
        a_goals = np.random.poisson(self.mu_a, self.iterations)
        home_wins = np.sum(h_goals > a_goals)
        draws = np.sum(h_goals == a_goals)
        away_wins = np.sum(h_goals < a_goals)
        over_2_5 = np.sum((h_goals + a_goals) > 2.5)
        
        diff = h_goals - a_goals
        ah_probs = {}
        for line in [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]:
            wins = np.sum((diff + line) > 0)
            ah_probs[f"AH {line:+.1f}"] = wins / self.iterations

        return {
            "mc_home_win": home_wins / self.iterations,
            "mc_draw": draws / self.iterations,
            "mc_away_win": away_wins / self.iterations,
            "mc_over_2.5": over_2_5 / self.iterations,
            "ah_probs": ah_probs
        }