from pawpal_system import Task, Pet


def test_task_toggle():
    task = Task(name="Walk", duration=30, priority=3)
    task.toggle_complete()
    assert task.is_completed is True
    task.toggle_complete()
    assert task.is_completed is False


def test_pet_task_addition():
    pet = Pet(name="Buddy", species="Dog", age=3)
    task = Task(name="Feed", duration=10, priority=5)
    pet.tasks.append(task)
    assert len(pet.tasks) == 1
