DEFAULT_ANNOUNCEMENT_TYPES = (
    {
        "code": "ANNUAL_REPORT",
        "label": "Annual Report",
        "description": "Full-year financial statements and strategic review.",
        "default_is_important": True,
    },
    {
        "code": "TRADING_UPDATE",
        "label": "Trading Update",
        "description": "Trading updates or statements covering recent performance.",
        "default_is_important": True,
    },
    {
        "code": "INTERIM_RESULTS",
        "label": "Interim / Half-Year Results",
        "description": "Half-year or interim financial statements.",
        "default_is_important": True,
    },
    {
        "code": "QUARTERLY_RESULTS",
        "label": "Quarterly Results",
        "description": "Quarterly financial updates or management statements.",
        "default_is_important": True,
    },
    {
        "code": "DIVIDEND",
        "label": "Dividend Announcement",
        "description": "Dividend declarations, changes, or cancellations.",
        "default_is_important": True,
    },
    {
        "code": "MAJOR_TRANSACTION",
        "label": "Major Transaction",
        "description": "Significant M&A, disposals, or capital transactions.",
        "default_is_important": True,
    },
    {
        "code": "BOARD_CHANGE",
        "label": "Board or Management Change",
        "description": "Changes to directors, key executives, or governance.",
        "default_is_important": False,
    },
    {
        "code": "GENERAL",
        "label": "General Announcement",
        "description": "General company news that does not fit other categories.",
        "default_is_important": False,
    },
)


KEYWORD_TYPE_MAP = {
    "ANNUAL_REPORT": [
        "annual report",
        "annual results",
        "full year results",
        "fy results",
    ],
    "TRADING_UPDATE": [
        "trading update",
        "trading statement",
        "q1 update",
        "q3 update",
        "sales update",
        "operational update",
    ],
    "INTERIM_RESULTS": [
        "interim results",
        "half year results",
        "half-year results",
        "h1 results",
    ],
    "QUARTERLY_RESULTS": [
        "q1 results",
        "q2 results",
        "q3 results",
        "q4 results",
        "quarterly results",
        "quarterly update",
    ],
    "DIVIDEND": [
        "dividend",
        "interim dividend",
        "final dividend",
        "special dividend",
    ],
    "MAJOR_TRANSACTION": [
        "acquisition",
        "disposal",
        "merger",
        "transaction",
        "investment",
        "financing",
        "placing",
        "rights issue",
    ],
    "BOARD_CHANGE": [
        "director",
        "board change",
        "management change",
        "appointment",
        "resignation",
        "ceo",
        "cfo",
    ],
}
