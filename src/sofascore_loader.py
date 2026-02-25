"""
SofaScore Data Loader Module

Loads and processes data from Sofascore (all_statistics.csv and all_shotmap.csv)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SofascoreDataLoader:
    """Loads and provides access to Sofascore data"""
    
    def __init__(self, data_dir: str = "data/sofascore/5_years_data"):
        self.data_dir = Path(data_dir)
        self._statistics_df = None
        self._shotmap_df = None
        self._match_cache = {}
    
    @property
    def statistics_df(self) -> pd.DataFrame:
        """Lazy load statistics data"""
        if self._statistics_df is None:
            print(f"   [Sofascore] Loading statistics data...")
            self._statistics_df = pd.read_csv(self.data_dir / "all_statistics.csv")
            # Convert date
            self._statistics_df['match_date'] = pd.to_datetime(self._statistics_df['match_date'])
            print(f"   [Sofascore] Loaded {len(self._statistics_df):,} stat rows")
        return self._statistics_df
    
    @property
    def shotmap_df(self) -> pd.DataFrame:
        """Lazy load shotmap data"""
        if self._shotmap_df is None:
            print(f"   [Sofascore] Loading shotmap data...")
            self._shotmap_df = pd.read_csv(self.data_dir / "all_shotmap.csv")
            # Convert date
            self._shotmap_df['match_date'] = pd.to_datetime(self._shotmap_df['match_date'])
            # Convert xg and xgot to numeric
            self._shotmap_df['xg'] = pd.to_numeric(self._shotmap_df['xg'], errors='coerce')
            self._shotmap_df['xgot'] = pd.to_numeric(self._shotmap_df['xgot'], errors='coerce')
            print(f"   [Sofascore] Loaded {len(self._shotmap_df):,} shot rows")
        return self._shotmap_df
    
    def get_matches_by_team(self, team_name: str, league: str = None) -> pd.DataFrame:
        """Get all matches for a team"""
        df = self.statistics_df
        
        # Filter by team
        mask = (df['home_team'] == team_name) | (df['away_team'] == team_name)
        
        if league:
            mask = mask & (df['tournament_name'] == league)
        
        df = df[mask]
        
        # Get unique matches
        matches = df.groupby('event_id').agg({
            'match_date': 'first',
            'tournament_name': 'first',
            'home_team': 'first',
            'away_team': 'first'
        }).reset_index()
        
        return matches.sort_values('match_date', ascending=False)
    
    def get_team_stats(self, team_name: str, league: str = None) -> pd.DataFrame:
        """Get all statistics for a team across matches"""
        df = self.statistics_df
        
        # Filter by team
        mask = (df['home_team'] == team_name) | (df['away_team'] == team_name)
        
        if league:
            mask = mask & (df['tournament_name'] == league)
        
        return df[mask].copy()
    
    def get_match_stats(self, event_id: int) -> pd.DataFrame:
        """Get statistics for a specific match"""
        if event_id in self._match_cache:
            return self._match_cache[event_id]
        
        df = self.statistics_df[self.statistics_df['event_id'] == event_id]
        
        # Pivot to get home/away values
        result = {}
        for _, row in df.iterrows():
            stat_name = row['stat_name']
            result[f"home_{stat_name.lower().replace(' ', '_')}"] = row['home_value']
            result[f"away_{stat_name.lower().replace(' ', '_')}"] = row['away_value']
        
        self._match_cache[event_id] = result
        return result
    
    def get_team_shots(self, team_name: str, league: str = None) -> pd.DataFrame:
        """Get all shots for a team (only with valid xg data)"""
        df = self.shotmap_df
        
        # Filter to valid xg data only
        df = df[df['xg'].notna()]
        
        # Filter by team
        mask = (df['home_team'] == team_name) | (df['away_team'] == team_name)
        
        if league:
            mask = mask & (df['tournament_name'] == league)
        
        return df[mask].copy()
    
    def get_match_shots(self, event_id: int) -> pd.DataFrame:
        """Get all shots for a specific match"""
        return self.shotmap_df[self.shotmap_df['event_id'] == event_id].copy()
    
    def calculate_team_xg_stats(self, team_name: str, is_home: bool, league: str = None, 
                                 recent_n: int = 30) -> Dict:
        """
        Calculate xG/xGOT statistics for a team (home or away)
        
        Returns:
            Dict with keys: xg_total, xgot_total, goals, shots, efficiency, n_samples
        """
        shots = self.get_team_shots(team_name, league)
        
        if is_home:
            team_shots = shots[shots['home_team'] == team_name]
        else:
            team_shots = shots[shots['away_team'] == team_name]
        
        # Get recent matches
        team_shots = team_shots.sort_values('match_date', ascending=False).head(recent_n * 20)  # Approximate
        
        # Group by match
        match_stats = team_shots.groupby('event_id').agg({
            'xg': 'sum',
            'xgot': 'sum',
            'outcome': lambda x: (x == 'goal').sum(),
            'match_date': 'first'
        }).reset_index()
        
        match_stats.columns = ['event_id', 'xg', 'xgot', 'goals', 'match_date']
        match_stats = match_stats.sort_values('match_date', ascending=False).head(recent_n)
        
        if len(match_stats) < 3:
            return {
                'xg_total': 1.3,
                'xgot_total': 1.0,
                'goals': 1.3,
                'shots': 10,
                'efficiency': 1.0,
                'n_samples': 0
            }
        
        return {
            'xg_total': match_stats['xg'].mean(),
            'xgot_total': match_stats['xgot'].mean(),
            'goals': match_stats['goals'].mean(),
            'shots': len(team_shots) / len(match_stats),  # Average shots per match
            'efficiency': match_stats['goals'].sum() / match_stats['xgot'].sum() if match_stats['xgot'].sum() > 0 else 1.0,
            'n_samples': len(match_stats)
        }
    
    def calculate_defensive_stats(self, team_name: str, is_home: bool, league: str = None,
                                   recent_n: int = 30) -> Dict:
        """
        Calculate defensive statistics for a team
        
        Returns:
            Dict with keys: xga, goals_conceded, shots_conceded, save_rate, quality_score, n_samples
        """
        shots = self.get_team_shots(team_name, league)
        
        # Filter to matches where this team was playing (based on is_home flag)
        if is_home:
            # Home team: shots where is_home = False (opponent shots)
            team_shots = shots[shots['home_team'] == team_name]
            opponent_shots = shots[(shots['home_team'] == team_name) & (shots['is_home'] == False)]
        else:
            # Away team: shots where is_home = True (opponent shots)  
            team_shots = shots[shots['away_team'] == team_name]
            opponent_shots = shots[(shots['away_team'] == team_name) & (shots['is_home'] == True)]
        
        # Group opponent shots by match
        if len(opponent_shots) == 0:
            return {
                'xga': 1.3,
                'goals_conceded': 1.3,
                'shots_conceded': 10,
                'save_rate': 0.7,
                'quality_score': 0.5,
                'n_samples': 0
            }
        
        match_stats = opponent_shots.groupby('event_id').agg({
            'xg': 'sum',
            'outcome': lambda x: (x == 'goal').sum(),
            'match_date': 'first'
        }).reset_index()
        
        match_stats.columns = ['event_id', 'xga', 'goals_conceded', 'match_date']
        
        # Sort by date and take recent_n
        match_stats = match_stats.sort_values('match_date', ascending=False).head(recent_n)
        
        if len(match_stats) < 3:
            return {
                'xga': 1.3,
                'goals_conceded': 1.3,
                'shots_conceded': 10,
                'save_rate': 0.7,
                'quality_score': 0.5,
                'n_samples': len(match_stats)
            }
        
        avg_xga = match_stats['xga'].mean()
        avg_goals_conceded = match_stats['goals_conceded'].mean()
        
        # Calculate save rate from raw shots
        total_shots = len(opponent_shots[opponent_shots['event_id'].isin(match_stats['event_id'])])
        total_goals = match_stats['goals_conceded'].sum()
        save_rate = 1 - (total_goals / total_shots) if total_shots > 0 else 0.7
        
        # Quality score
        xga_score = max(0, 100 - avg_xga * 30)
        quality_score = (xga_score + save_rate * 100) / 2 / 100
        
        return {
            'xga': avg_xga,
            'goals_conceded': avg_goals_conceded,
            'shots_conceded': total_shots / len(match_stats),
            'save_rate': save_rate,
            'quality_score': quality_score,
            'n_samples': len(match_stats)
        }
    
    def get_available_leagues(self) -> List[str]:
        """Get list of available leagues"""
        return sorted(self.statistics_df['tournament_name'].unique().tolist())
    
    def get_team_name_mapping(self) -> Dict[str, str]:
        """Get mapping of team names from Sofascore to other formats"""
        teams = pd.concat([
            self.statistics_df['home_team'],
            self.statistics_df['away_team']
        ]).unique()
        
        return {team: team for team in teams}
    
    def calculate_corner_stats(self, team_name: str, is_home: bool, league: str = None,
                                recent_n: int = 20) -> Dict:
        """
        Calculate corner statistics for a team
        
        Returns:
            Dict with keys: avg_corners, n_samples
        """
        df = self.statistics_df
        
        # Filter to corner kicks
        df = df[df['stat_name'] == 'Corner kicks']
        
        # Filter by team
        if is_home:
            df = df[df['home_team'] == team_name]
        else:
            df = df[df['away_team'] == team_name]
        
        # Filter by league if specified
        if league:
            df = df[df['tournament_name'] == league]
        
        if len(df) < 3:
            return {'avg_corners': 5.0, 'n_samples': 0}
        
        # Get recent matches
        df = df.sort_values('match_date', ascending=False).head(recent_n)
        
        if is_home:
            avg_corners = df['home_value'].mean()
        else:
            avg_corners = df['away_value'].mean()
        
        return {
            'avg_corners': avg_corners if not pd.isna(avg_corners) else 5.0,
            'n_samples': len(df)
        }


# Singleton instance
_sofascore_loader = None

def get_sofascore_loader(data_dir: str = "data/sofascore/5_years_data") -> SofascoreDataLoader:
    """Get the Sofascore data loader singleton"""
    global _sofascore_loader
    if _sofascore_loader is None:
        _sofascore_loader = SofascoreDataLoader(data_dir)
    return _sofascore_loader
