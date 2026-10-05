# Math AI Project Guidelines

## Project Purpose

This project is a personalized AI-assisted training system for high school mathematics students.

The goal is not to build a simple question-answering chatbot.

The core learning loop is:

Student practice
→ Collect learning data
→ Diagnose knowledge gaps
→ Analyze error types
→ Build student mastery profile
→ Recommend personalized exercises
→ Generate personalized learning plans
→ Practice again
→ Update the student profile

The system should help students understand:

1. What they do not know.
2. Why they made mistakes.
3. What they should learn next.
4. What exercises they should practice next.

AI should support mathematical thinking, not replace it.

## Educational Principles

The system follows these principles:

- Teacher-led, AI-assisted.
- AI should not directly replace mathematical reasoning.
- Prefer hints and guided thinking over immediately showing full answers.
- Student mastery should be calculated from structured learning data.
- Large language models should not determine mastery scores directly.
- AI-generated educational content must be treated as assistive content.
- Personalized recommendations should respect prerequisite knowledge.

For example:

If a student performs poorly on parameterized function problems,
the system should first inspect prerequisite knowledge such as:

- function monotonicity
- maximum and minimum values

before recommending more difficult parameter problems.

## Technology Stack

The first MVP should use:

- Python 3
- Streamlit
- SQLite
- pandas
- matplotlib

Use Python's built-in `sqlite3` module initially.

Do NOT introduce the following unless explicitly requested:

- React
- Vue
- Docker
- Redis
- microservices
- complex cloud infrastructure
- machine learning frameworks

Keep the first version simple and understandable.

## MVP Scope

The first version focuses only on the high school mathematics topic:

Function（函数）

Initial knowledge points:

- K001: 函数概念
- K002: 定义域
- K003: 函数单调性
- K004: 函数最值
- K005: 含参数函数

Do not expand into the entire high school mathematics curriculum until the function module works correctly.

## Development Roadmap

Implement features incrementally.

### V0.1 Database Foundation

Create:

- knowledge_points table
- questions table
- attempts table

Initialize:

- K001-K005 knowledge points
- several test questions

Verify database creation, insertion, and querying.

### V0.2 Student Training Page

Use Streamlit to implement:

- display one question
- A/B/C/D choices
- submit answer
- automatic scoring
- correct/incorrect feedback
- next question

### V0.3 Learning Data Collection

Record:

- student_id
- question_id
- user_answer
- correctness
- answer time
- hint count
- retry count
- timestamp

### V0.4 Knowledge Mastery

Create:

services/mastery.py

Initially use a rule-based mathematical model rather than machine learning.

Example:

M = 0.5A + 0.2R + 0.15S + 0.15D

Where:

- A = overall accuracy
- R = recent accuracy
- S = stability
- D = difficulty performance

Normalize all values to 0-1.

### V0.5 Student Knowledge Profile

Display mastery levels for each knowledge point.

Example:

函数概念      92%
定义域        84%
函数单调性    67%
函数最值      53%
含参数函数    35%

### V0.6 Personalized Recommendation

Create:

services/recommendation.py

Recommendations should consider:

- mastery level
- prerequisite relationships
- question difficulty
- recent practice history

Do not simply recommend more questions from the weakest advanced topic.

Always check prerequisite weaknesses first.

### V0.7 AI Feedback

Only after the deterministic learning system works should an LLM be introduced.

The LLM may:

- explain learning reports
- generate personalized natural-language feedback
- provide progressive hints
- help generate learning-plan descriptions

The LLM must NOT directly determine:

- mastery scores
- correctness of objective questions
- student grades
- prerequisite relationships

## Error Classification

The first version may classify mistakes into:

- K: Knowledge error
- C: Calculation error
- L: Logical reasoning error
- M: Method selection error
- R: Reading/comprehension error
- S: Strategy error

These classifications should be stored as structured data where possible.

## Hint System

Prefer progressive hints.

Recommended levels:

Level 1:
General direction.

Level 2:
Relevant mathematical method.

Level 3:
Key intermediate step.

Level 4:
Full solution.

Do not show the full solution immediately unless necessary.

## Project Structure

Prefer the following structure:

math_ai/
    app.py
    init_db.py
    README.md
    requirements.txt
    .gitignore

    database/
        __init__.py
        database.py

    services/
        __init__.py
        mastery.py
        recommendation.py
        feedback.py
        learning_plan.py

    data/
        questions.csv

    pages/
        training.py
        profile.py
        mistakes.py
        plan.py

    tests/

## Code Organization

Keep responsibilities separated.

Examples:

database/database.py
- database connections
- database access

services/mastery.py
- mastery calculation only

services/recommendation.py
- recommendation logic only

services/feedback.py
- AI/natural-language feedback only

services/learning_plan.py
- personalized learning-plan generation

Do not place business logic directly inside Streamlit page code when it can be separated into a service module.

## Language Conventions

- User-facing interface text should primarily use Simplified Chinese, including labels, buttons, hints, feedback, and learning reports.
- Code identifiers should use English, including module, class, function, variable, table, and column names.

## Coding Style

Follow standard Python conventions.

Use:

- clear function names
- descriptive variable names
- type hints when useful
- docstrings for important functions
- UTF-8 encoding

Prefer simple readable code over unnecessary abstraction.

## Database Rules

Use SQLite for the MVP.

Enable foreign-key constraints.

Database initialization scripts must be safe to run multiple times.

Avoid duplicate seed data.

Do not delete existing student learning records unless explicitly requested.

## Testing

Add tests when executable functionality is introduced.

At minimum test:

- database initialization
- database insertion
- database querying
- mastery calculation
- recommendation rules

Tests should not require:

- API credentials
- internet access
- external paid services

## Security

Never commit:

- API keys
- passwords
- private student information
- `.env` files

Use environment variables for secrets.

For example:

OPENAI_API_KEY

If OpenAI APIs are later introduced, verify current API usage against official OpenAI documentation.

## Git

Keep commits focused.

Suggested commit messages:

- Add initial database schema
- Add function question seed data
- Add student training page
- Add mastery calculation
- Add personalized recommendation logic

Before committing, review:

git status --short

and:

git diff --check

## Codex Working Rules

Before making major changes:

1. Inspect the existing project.
2. Explain briefly what will change.
3. Implement only the requested development stage.
4. Run relevant tests.
5. Fix errors before stopping.
6. Summarize:
   - files created
   - files modified
   - commands executed
   - test results
   - recommended next step

Do not implement future roadmap stages unless explicitly requested.

Prioritize a small working MVP over a large incomplete architecture.
