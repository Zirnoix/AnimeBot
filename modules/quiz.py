# modules/quiz_reset.py

from datetime import datetime, timedelta

def get_days_until_reset():
    """Retourne le nombre de jours restants avant la fin du mois."""
    today = datetime.today()
    next_month = today.replace(day=28) + timedelta(days=4)  # Cela garantit le passage au mois suivant
    reset_day = next_month.replace(day=1)
    delta = reset_day - today
    return delta.days
