from langchain.tools import tool

@tool
def schedule_task(task_description: str, time_str: str) -> str:
    """
    Schedules a task to run at a specific time. 
    (Currently simulated backend).
    """
    return f"Task '{task_description}' has been successfully scheduled for {time_str}."
