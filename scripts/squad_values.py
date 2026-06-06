"""2026 World Cup squad market values (Transfermarkt), by canonical team name.

A third, independent lens on team strength: results-blind (it values players, not
wins), and the one a bookmaker-style model leans on. Source: Transfermarkt combined
squad values, June 2026 (£m). Units are arbitrary for our use (we compare shares).
"""

# canonical WC2026_TEAMS name -> combined squad value (£m, Transfermarkt, Jun 2026)
SQUAD_VALUE = {
    "France": 1320, "England": 1130, "Spain": 1090, "Portugal": 880, "Germany": 862.97,
    "Brazil": 788.78, "Netherlands": 723.93, "Argentina": 707.76, "Norway": 519.68,
    "Belgium": 469.45, "Ivory Coast": 459.07, "Morocco": 422.15, "Senegal": 408.92,
    "Turkey": 408.74, "Sweden": 370.25, "Uruguay": 350.9, "Croatia": 333.51, "USA": 327.03,
    "Ecuador": 325.3, "Switzerland": 288.46, "Colombia": 263.95, "Japan": 241.16,
    "Austria": 234.94, "Algeria": 222.75, "Ghana": 199.64, "Canada": 175.58, "Mexico": 168.27,
    "Czech Republic": 164.45, "Scotland": 152.39, "Paraguay": 135.89,
    "Bosnia & Herzegovina": 129.04, "DR Congo": 128.91, "South Korea": 123.07, "Egypt": 116.48,
    "Australia": 63.7, "Uzbekistan": 60.74, "Tunisia": 60.06, "Cape Verde": 48.59,
    "Haiti": 48.09, "South Africa": 39.61, "Saudi Arabia": 32.09, "New Zealand": 30.57,
    "Panama": 30.12, "Iran": 28.24, "Curaçao": 22.51, "Iraq": 18.21, "Qatar": 17.24,
    "Jordan": 16.89,
}
