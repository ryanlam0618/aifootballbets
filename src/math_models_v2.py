import math
import numpy as np
from scipy.stats import poisson
from scipy.optimize import minimize

# ❌ 千萬不要在這裡 import data_modules 或 config

class Glicko2System:
    """
    Glicko-2 評分系統
    """
    def __init__(self, tau=0.5, base_rating=1500, base_rd=350, base_vol=0.06):
        self.tau = tau
        self.base_rating = base_rating
        self.base_rd = base_rd
        self.base_vol = base_vol
        self.ratings = {}

    def get_rating(self, team):
        if team not in self.ratings:
            self.ratings[team] = {'rating': self.base_rating, 'rd': self.base_rd, 'vol': self.base_vol}
        return self.ratings[team]

    def _g(self, phi):
        return 1 / math.sqrt(1 + 3 * (phi ** 2) / (math.pi ** 2))

    def _E(self, mu, mu_j, phi_j):
        return 1 / (1 + math.exp(-self._g(phi_j) * (mu - mu_j)))

    def update_ratings(self, home, away, h_goals, a_goals, xg_home=None, xg_away=None):
        """
        更新評分系統

        Args:
            home: 主隊名稱
            away: 客隊名稱
            h_goals: 主隊進球
            a_goals: 客隊進球
            xg_home: 主隊 xG (可選，用於加權更新)
            xg_away: 客隊 xG (可選，用於加權更新)
        """
        if h_goals > a_goals: s_h = 1; s_a = 0
        elif h_goals == a_goals: s_h = 0.5; s_a = 0.5
        else: s_h = 0; s_a = 1

        # 如果有 xG 數據，計算加權結果
        # xG 越高，表示球隊實際表現比預期好/壞
        if xg_home is not None and xg_away is not None:
            # 計算 xG 差異
            xg_diff = xg_home - xg_away
            goal_diff = h_goals - a_goals

            # 如果進球數與 xG 預期不符，調整結果權重
            # 例如：xG 領先但輸球，可能表示運氣不佳，給予部分積分
            if (xg_diff > 0.3 and s_h == 0):  # xG 領先但輸球
                s_h = 0.3  # 降低懲罰
            elif (xg_diff < -0.3 and s_h == 1):  # xG 落後但贏球
                s_h = 0.7  # 降低獎勵

        def scale_down(r, rd):
            return (r - 1500) / 173.7178, rd / 173.7178
        
        def scale_up(mu, phi):
            return 173.7178 * mu + 1500, 173.7178 * phi

        rh, rdh = scale_down(self.get_rating(home)['rating'], self.get_rating(home)['rd'])
        ra, rda = scale_down(self.get_rating(away)['rating'], self.get_rating(away)['rd'])

        g_phi_a = self._g(rda)
        g_phi_h = self._g(rdh)
        
        E_h = self._E(rh, ra, rda)
        E_a = self._E(ra, rh, rdh)
        
        v_h = 1 / (g_phi_a ** 2 * E_h * (1 - E_h))
        v_a = 1 / (g_phi_h ** 2 * E_a * (1 - E_a))
        
        new_rh = rh + (1 / (1/rdh**2 + 1/v_h)) * g_phi_a * (s_h - E_h)
        new_ra = ra + (1 / (1/rda**2 + 1/v_a)) * g_phi_h * (s_a - E_a)
        
        new_rdh = math.sqrt(1 / (1/rdh**2 + 1/v_h))
        new_rda = math.sqrt(1 / (1/rda**2 + 1/v_a))

        final_rh, final_rdh = scale_up(new_rh, new_rdh)
        final_ra, final_rda = scale_up(new_ra, new_rda)
        
        self.ratings[home] = {'rating': final_rh, 'rd': final_rdh, 'vol': self.base_vol}
        self.ratings[away] = {'rating': final_ra, 'rd': final_rda, 'vol': self.base_vol}

    def expected_win_prob(self, home, away):
        r_h = self.get_rating(home)['rating']
        r_a = self.get_rating(away)['rating']
        return 1 / (1 + 10 ** ((r_a - r_h) / 400))

class LineupModel:
    """
    基於球員評分 (Player Ratings) 的預測模型
    """
    def __init__(self, lineup_data):
        self.data = lineup_data

    def calculate_strength(self):
        if not self.data: return None, None
        
        home_team = self.data.get('home_team', {})
        away_team = self.data.get('away_team', {})
        
        def get_team_score(team_obj):
            starters = team_obj.get('starters', [])
            if not starters: return 0
            
            total_rating = 0
            count = 0
            for p in starters:
                try:
                    r = float(p.get('rating', 0))
                    if r > 0:
                        total_rating += r
                        count += 1
                except: continue
            
            return total_rating / count if count > 0 else 0

        h_score = get_team_score(home_team)
        a_score = get_team_score(away_team)
        
        return h_score, a_score

    def predict_win_prob(self):
        h_score, a_score = self.calculate_strength()
        if not h_score or not a_score: return 0.5 
        
        diff = h_score - a_score
        adjusted_diff = diff + 0.2
        
        win_prob = 1 / (1 + math.exp(-1.5 * adjusted_diff))
        return win_prob

class OptimizedDixonColes:
    """
    優化版 Dixon-Coles 模型
    """
    def __init__(self, home_expect, away_expect, rho=-0.1):
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

# ✅ 補上這個類別，讓 app.py 可以正確 import
class MonteCarloSimulator:
    """
    蒙地卡羅模擬 (v2)
    """
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