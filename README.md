# pysky
A Bluesky API library focused on higher-level database-backed features

## Features:

### Database logging of all API calls, used for:
   
   * session caching across processes
   * user did/handle caching
   * throttling / rate limit management
   * cursor management (remember where you left off fetching data from a cursor-managed endpoint in prior sessions)
   * alerting through Bluesky messages (throttled to prevent flooding)

Database access through peewee ORM, tested with PostgreSQL and SQLite.
