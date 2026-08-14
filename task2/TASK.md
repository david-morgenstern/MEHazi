# Task 2 — PySpark

English translation of the assignment brief (page 2 of the original document).

1. Generate a large dataset (100 thousand – 1 million rows) that imitates
   sensor data. Create the following columns:
   - Sensor_ID (e.g. 'a323frt', 'df21fs1', ...)
   - Date (e.g. 2025.10.20, 2025.10.09)
   - Location (e.g. Hungary, Germany, ...)
   - Parameter (Offset, Noise, Temperatur, ...)
   - Value (numeric values)
   - Status (categorical values: Good, Bad)

2. Write a PySpark script that loads the generated data.
   - Perform at least 3 complex transformations. For example:
   - Use of window functions
   - GroupBy + aggregation over multiple fields
   - Pivot/unpivot
   - String or date manipulation

3. Save the processed data in Parquet format. Design the table so that the data
   types match the fields of the PySpark DataFrame.

4. Choose a simple database (e.g. SQLite, a PostgreSQL Docker container), or
   one you can easily work with:
   - Create a table in the database into which the data previously processed
     with PySpark (the generated data) can be loaded
   - Write a Python script that reads the processed data out of PySpark and
     loads it into the database
   - Write at least 3 SQL queries against the database with which you verify
     the integrity of the data and the correctness of the processing

## Basic requirements

- The Python script should be modular
- Write short docstrings or use type hints for the main functions
- Use GIT for version control (build the solutions in a GIT repository and
  share it with us)
