# Legacy -- v0.7 (Stable Baseline)

## Overview

Legacy is a structured AI-assisted identity preservation prototype built
with Flask.

Version 0.7 represents the first stable web-enabled release with:

-   Working subject creation
-   Consent management
-   Structured interview system
-   Core Summary generation
-   AI-influenced guidance responses
-   Markdown export capability

This version is intentionally minimal and stable. It serves as the
rollback anchor for future experimentation.

------------------------------------------------------------------------

## Core Architecture

### Backend

-   Python 3.9
-   Flask
-   Local JSON profile storage
-   OpenAI API integration (Core Summary + Guidance)

### Profile Structure

Each subject profile contains:

-   subject.display_name
-   consent settings
-   entries (interview + guidance entries)
-   core_summary
-   core_summary_meta

Entries contain: - timestamp_utc - category - prompt - answer - tags
(currently unused but present)

------------------------------------------------------------------------

## Functional Flow

1.  Create subject
2.  Enable consent
3.  Complete interview prompts
4.  Update Core Summary
5.  Ask guidance questions
6.  Export markdown summary

Guidance responses are influenced by: - Recent entries - Core Summary

------------------------------------------------------------------------

## Stability Notes

v0.7 intentionally avoids:

-   Structured memory anchors (people, year, importance)
-   Advanced retrieval scoring
-   Complex UI enhancements
-   Typed schema enforcement

This keeps the system predictable and easy to debug.

------------------------------------------------------------------------

## Environment Setup

Activate virtual environment:

    source venv/bin/activate

Set API key:

    export OPENAI_API_KEY="your_key_here"

Run application:

    python3 src/webapp.py

------------------------------------------------------------------------

## Purpose of v0.7

v0.7 exists as:

-   A functional proof of concept
-   A stable demonstration build
-   A rollback version for safe experimentation
-   A baseline for Masters application submission

------------------------------------------------------------------------

## Next Phase (Planned)

-   Retrieval quality improvements
-   Structured memory fields
-   Summary refinement
-   UI polish
-   Mobile pathway planning

------------------------------------------------------------------------

End of v0.7 README
