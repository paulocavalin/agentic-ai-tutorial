def run(city: str) -> str:
    city_l = city.lower()
    if city_l == "san francisco":
        return "72"
    if city_l == "paris":
        return "75"
    if city_l == "tokyo":
        return "73"
    return "70"
