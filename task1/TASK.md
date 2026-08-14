# Task 1 — Data Collection and Data Preparation

English translation of the assignment brief (page 1 of the original document).

1. Choose a publicly available API or Open Dataset. For example:
   - Weather API: OpenWeatherMap, AccuWeather
   - Stock/exchange rate API: Exchangeratesapi.io
   - Kaggle, data.gov

2. Using Python, collect data from the API from at least 3 different points in
   time or with 3 different parameters (e.g. the weather of different cities,
   the price of different products, etc.).

3. Save the raw data in Parquet or CSV format.

4. Load the saved raw data using Python (pandas).

5. Perform at least 3–4 cleaning and transformation steps on the data. For
   example:
   - Handling missing values
   - Converting the date format
   - Removing redundant columns, creating new columns

6. Save the prepared data into a clean Parquet or CSV file.

7. Create a simple Tableau or Spotfire dashboard (using a trial version) that
   displays the prepared, cleaned data.
   - Use the table exported in point 6 as the data source
   - Create at least 2–3 different visualisations
   - The dashboard should be interactive

8. Write a short (max. 1 page) description of the processing steps, the data
   source and the cleaning decisions.

## Basic requirements

- The Python script should be modular
- Write short docstrings or use type hints for the main functions
- Use GIT for version control (build the solutions in a GIT repository and
  share it with us)

## Optional

- The Python script should include a basic logging setup. At least three log
  messages should appear at the key steps of the process (e.g. data retrieval,
  file save, start/end of data transformation)
- Write at least 1–2 short unit tests (e.g. with Pytest) that verify the
  behaviour of the main functions (e.g. data transformation, cleaning)
