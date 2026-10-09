"""Edit only the four literal inputs; run with the course launcher."""

from tasks.report import report

rows = [{"owner": "member-a", "title": "Reading", "minutes": 45}]
viewer = "member-a"
minimum = 30
expected = "title,minutes,same_title\nReading,45,1"
actual = report(rows, viewer, minimum)
print(f"expected={expected!r}\nactual={actual!r}")
assert actual == expected
