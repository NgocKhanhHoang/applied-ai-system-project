"""Tests for the PawPal+ core system."""

from pawpal_system import Task, Pet, Priority


def test_mark_complete_changes_status():
    # Arrange: a fresh task starts out NOT completed.
    task = Task("Morning walk", 30, Priority.HIGH)
    assert task.completed is False        # sanity check before we act

    # Act: mark it done.
    task.mark_complete()

    # Assert: the status actually flipped to True.
    assert task.completed is True


def test_add_task_increases_pet_task_count():
    # Arrange: a pet with no tasks yet.
    pet = Pet(name="Rex", species="dog", food="kibble")
    assert len(pet.tasks) == 0            # starts empty

    # Act: add one task.
    pet.add_task(Task("Feed dinner", 10, Priority.MEDIUM))

    # Assert: the pet's task count went up by one.
    assert len(pet.tasks) == 1
