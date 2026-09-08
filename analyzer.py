from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from database import FoodDatabase


class FoodAnalyzer:
    def __init__(self, db: FoodDatabase):
        self.db = db

    def get_expiry_status(self, expiry_date: str) -> Tuple[str, str, str]:
        today = datetime.now().date()
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        days_left = (expiry - today).days

        if days_left < 0:
            return "EXPIRED", "danger", f"Expired {abs(days_left)}d ago"
        elif days_left == 0:
            return "EXPIRES TODAY", "danger", "Use today!"
        elif days_left == 1:
            return "EXPIRES TOMORROW", "warning", "Use tomorrow"
        elif days_left <= 3:
            return f"EXPIRES IN {days_left} DAYS", "warning", f"{days_left} days left"
        elif days_left <= 5:
            return f"EXPIRES IN {days_left} DAYS", "info", f"{days_left} days left"
        else:
            return f"EXPIRES IN {days_left} DAYS", "success", f"{days_left} days left"

    def get_priority_items(self, user_id: int = None) -> List[Dict]:
        items = self.db.get_all_items(user_id)
        today = datetime.now().date()
        priority_items = []
        for item in items:
            days_left = (datetime.strptime(item["expiry_date"], "%Y-%m-%d").date() - today).days
            status, badge, _ = self.get_expiry_status(item["expiry_date"])
            if days_left <= 3:
                item["status"] = status
                item["badge"] = badge
                item["days_left"] = days_left
                priority_items.append(item)
        return priority_items

    def suggest_recipe(self, expiring_items: List[Dict]) -> Dict:
        if not expiring_items:
            return {
                "name": "No items expiring",
                "description": "Your inventory is fresh!",
                "ingredients": [],
                "instructions": [],
                "prep_time": "0 min",
                "difficulty": "N/A"
            }

        categories = [item.get("category_name", item.get("category", "")) for item in expiring_items]
        names = [item["name"] for item in expiring_items]

        recipes = {
            "leftovers": {
                "name": "Leftover Stir-Fry",
                "description": "A quick and easy way to use up leftover vegetables and proteins",
                "ingredients": ["All leftover vegetables", "Soy sauce", "Garlic", "Ginger", "Oil"],
                "instructions": [
                    "Chop all vegetables into bite-sized pieces",
                    "Heat oil in a large pan or wok",
                    "Add garlic and ginger, sauté for 30 seconds",
                    "Add vegetables and stir-fry for 5-7 minutes",
                    "Add soy sauce and toss to combine",
                    "Serve hot over rice or noodles"
                ],
                "prep_time": "15 min",
                "difficulty": "Easy"
            },
            "vegetables": {
                "name": "Roasted Vegetable Medley",
                "description": "Simple roasted vegetables with herbs and olive oil",
                "ingredients": ["Mixed vegetables", "Olive oil", "Salt", "Pepper", "Herbs"],
                "instructions": [
                    "Preheat oven to 200°C (400°F)",
                    "Chop vegetables into uniform pieces",
                    "Toss with olive oil, salt, and pepper",
                    "Spread on a baking sheet in single layer",
                    "Roast for 25-30 minutes until golden",
                    "Sprinkle with fresh herbs before serving"
                ],
                "prep_time": "30 min",
                "difficulty": "Easy"
            },
            "fruits": {
                "name": "Mixed Fruit Smoothie",
                "description": "A refreshing blend of fresh fruits",
                "ingredients": ["Mixed fruits", "Yogurt", "Honey", "Ice"],
                "instructions": [
                    "Wash and chop all fruits",
                    "Add fruits to blender",
                    "Add yogurt and honey",
                    "Blend until smooth",
                    "Add ice if needed",
                    "Serve immediately"
                ],
                "prep_time": "10 min",
                "difficulty": "Easy"
            },
            "dairy": {
                "name": "Cheese Omelette",
                "description": "A classic protein-packed breakfast",
                "ingredients": ["Eggs", "Cheese", "Butter", "Salt", "Pepper"],
                "instructions": [
                    "Beat eggs with salt and pepper",
                    "Heat butter in a non-stick pan",
                    "Pour in eggs and let set slightly",
                    "Add cheese to one half",
                    "Fold omelette in half",
                    "Cook until cheese melts"
                ],
                "prep_time": "10 min",
                "difficulty": "Easy"
            },
            "meat": {
                "name": "Quick Meat Stir-Fry",
                "description": "Fast and flavorful meat dish",
                "ingredients": ["Meat strips", "Soy sauce", "Garlic", "Vegetables", "Rice"],
                "instructions": [
                    "Slice meat into thin strips",
                    "Marinate in soy sauce for 5 minutes",
                    "Heat oil in a hot pan",
                    "Cook meat quickly until browned",
                    "Add vegetables and stir-fry",
                    "Serve over cooked rice"
                ],
                "prep_time": "20 min",
                "difficulty": "Easy"
            },
            "bread": {
                "name": "French Toast",
                "description": "Classic breakfast using slightly stale bread",
                "ingredients": ["Bread slices", "Eggs", "Milk", "Cinnamon", "Butter"],
                "instructions": [
                    "Whisk eggs, milk, and cinnamon",
                    "Dip bread slices in mixture",
                    "Heat butter in a pan",
                    "Cook bread until golden on both sides",
                    "Serve with maple syrup or fruit"
                ],
                "prep_time": "15 min",
                "difficulty": "Easy"
            },
            "grains": {
                "name": "Fried Rice",
                "description": "Perfect for using leftover rice",
                "ingredients": ["Day-old rice", "Eggs", "Vegetables", "Soy sauce", "Oil"],
                "instructions": [
                    "Heat oil in a wok or large pan",
                    "Scramble eggs and set aside",
                    "Add vegetables and cook briefly",
                    "Add rice and stir-fry on high heat",
                    "Add soy sauce and toss well",
                    "Return eggs and mix together"
                ],
                "prep_time": "15 min",
                "difficulty": "Easy"
            }
        }

        if "Leftovers" in categories:
            return recipes["leftovers"]
        elif "Vegetables" in categories:
            return recipes["vegetables"]
        elif "Fruits" in categories:
            return recipes["fruits"]
        elif "Dairy" in categories:
            return recipes["dairy"]
        elif "Meat" in categories:
            return recipes["meat"]
        elif "Bread" in categories or "Bakery" in categories:
            return recipes["bread"]
        elif "Grains" in categories:
            return recipes["grains"]
        else:
            return {
                "name": f"Use {', '.join(names[:3])}",
                "description": "Don't let these items go to waste!",
                "ingredients": names[:5],
                "instructions": [
                    "Check what you have available",
                    "Plan a simple meal around these items",
                    "Cook and enjoy before they expire!"
                ],
                "prep_time": "Varies",
                "difficulty": "Easy"
            }

    def calculate_waste_reduction_score(self, user_id: int = None) -> Dict:
        stats = self.db.get_waste_stats(30, user_id)
        all_items = self.db.get_all_items(user_id)
        total_tracked = len(all_items) + stats["total_items_wasted"]

        if total_tracked == 0:
            return {"score": 0, "message": "Start tracking food to get your score!", "grade": "N/A"}

        wasted_ratio = stats["total_items_wasted"] / max(total_tracked, 1)
        score = max(0, 100 - int(wasted_ratio * 100))

        if score >= 90:
            grade = "A+"
            message = "Outstanding! You're a food waste champion!"
        elif score >= 80:
            grade = "A"
            message = "Excellent! You're doing amazing!"
        elif score >= 70:
            grade = "B"
            message = "Great job! Keep it up!"
        elif score >= 60:
            grade = "C"
            message = "Good progress! A few items slipping through."
        elif score >= 40:
            grade = "D"
            message = "Room for improvement. Check expiring items more often."
        else:
            grade = "F"
            message = "Let's work on reducing waste. Use the alerts feature!"

        return {"score": score, "message": message, "grade": grade}

    def generate_weekly_report(self) -> str:
        stats = self.db.get_waste_stats(7)
        expiring = self.db.get_expiring_items(3)
        score_data = self.calculate_waste_reduction_score()

        report = []
        report.append("=" * 55)
        report.append("       WEEKLY FOOD WASTE REPORT")
        report.append("=" * 55)
        report.append(f"\nPeriod: Last 7 days")
        report.append(f"Items Wasted: {stats['total_items_wasted']}")
        report.append(f"Estimated Cost Lost: ${stats['total_cost_lost']:.2f}")
        report.append(f"\nWaste Reduction Score: {score_data['score']}/100 ({score_data['grade']})")
        report.append(f"Status: {score_data['message']}")

        if expiring:
            report.append(f"\n--- ACTION NEEDED: {len(expiring)} items expiring soon ---")
            for item in expiring[:5]:
                status, badge, _ = self.get_expiry_status(item["expiry_date"])
                cat_name = item.get("category_name", item.get("category", ""))
                report.append(f"  * {item['name']} ({cat_name}) - {status}")

        if stats["waste_by_reason"]:
            report.append("\n--- Top Waste Reasons ---")
            for reason_data in stats["waste_by_reason"]:
                report.append(f"  * {reason_data['reason']}: {reason_data['count']} items (${reason_data['cost']:.2f})")

        report.append("\n" + "=" * 55)
        return "\n".join(report)
