CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    ticket_link TEXT NOT NULL,
    time_spent REAL NOT NULL,
    comments TEXT,
    category TEXT NOT NULL,
    date TEXT
);

CREATE TABLE schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    activity TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    link TEXT,  -- Add link column
    category TEXT,  -- Add category column
    moved_to_log_work INTEGER DEFAULT 0  -- Add moved_to_log_work column
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);
