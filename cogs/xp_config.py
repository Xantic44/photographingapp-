"""
Shared XP configuration and scaling helpers.
"""

# Constants
XP_BASE_GAIN_RANGE = (10, 20)  # Base XP gain from messages
XP_MSG_COOLDOWN = 15  # Reduced cooldown (was 20)
PASSIVE_XP_RANGE = (3, 8)  # Base passive XP for online members
VOICE_XP_RANGE = (5, 12)  # Base XP for being in voice
FUNPOINTS_PASSIVE_RANGE = (1, 5)
PASSIVE_INTERVAL_MINUTES = 5  # How often passive XP is given


def get_xp_multiplier(level: int) -> float:
	"""Calculate XP multiplier based on level.

	Higher levels earn more XP to compensate for increased requirements.
	Multiplier scales from 1.0x at level 1 to ~4x at level 100.
	"""
	if level <= 1:
		return 1.0
	elif level <= 10:
		# Levels 1-10: 1.0x to 1.5x
		return 1.0 + (level - 1) * 0.05
	elif level <= 25:
		# Levels 11-25: 1.5x to 2.0x
		return 1.5 + (level - 10) * 0.033
	elif level <= 50:
		# Levels 26-50: 2.0x to 3.0x
		return 2.0 + (level - 25) * 0.04
	else:
		# Levels 51+: 3.0x to 4.0x (capped)
		return min(4.0, 3.0 + (level - 50) * 0.02)
