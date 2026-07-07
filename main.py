from pawpal_system import Task, Pet, Owner, Scheduler, Priority

ice_cream = Pet(name="Ice Cream", species="dog", food="meat")
meo = Pet(name="Meo", species="cat", food="tuna")

ice_cream.add_task(Task("Morning walk", 60, Priority.HIGH, location="park"))
ice_cream.add_task(Task("Feed dinner", 10, Priority.MEDIUM))
meo.add_task(Task("Brushing", 15, Priority.LOW, location="living room"))

owner = Owner(name="Lilia", pets=[ice_cream, meo], available_minutes=120)

scheduler = Scheduler()
scheduler.generate_plan(owner)
scheduler.display()