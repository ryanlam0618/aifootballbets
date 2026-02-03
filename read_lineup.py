import os
with open('src/lineup_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the get_lineup method
start_marker = 'class LineupAggregator:'
end_marker = '    def get_player_ratings'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

print(f'Start: {start_idx}, End: {end_idx}')
print(f'Method length: {end_idx - start_idx}')

# Save to file instead
with open('current_get_lineup.txt', 'w', encoding='utf-8') as f:
    f.write(content[start_idx:end_idx])
print('Saved to current_get_lineup.txt')
