# Task 3 — Frontend and Backend

English translation of the assignment brief (page 3 of the original document).

Create a simple web interface that displays aggregated information derived from
the sensor data processed in the second task.

1. Create a simple Python-based REST API (e.g. using Flask or FastAPI) that can
   serve data from the database loaded in the second task.
   - The API should have at least 2–3 endpoints:
     1. An endpoint that returns the list of "Sensor_ID"s.
     2. An endpoint that returns all processed data belonging to a given
        "Sensor_ID" (or a summary statistic, e.g. the average value).
   - Use a pydantic model (in the case of FastAPI) or marshmallow (in the case
     of Flask) to validate the data.
   - There should be basic error and status code handling.

2. Create a simple HTML page that uses CSS and JavaScript.
   - Using JavaScript, call the backend API and display the data on the web
     page. For example:
     1. A drop-down list of the "Sensor_ID"s, and after a selection the data of
        the given sensor is displayed
     2. A table in which the data can be sorted or filtered

3. Create a README.md file that contains
   - The main steps of the pipeline (data collection → processing → loading →
     API → frontend)
   - The steps for running it (Docker / manually)
