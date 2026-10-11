"""Request bodies shared by the API tests."""

LOST_BACKPACK = {
    "type": "lost",
    "description": "I lost my dark blue backpack near the university library.",
    "category": "bag",
    "color": "dark blue",
    "location": "Main Library",
    "occurred_at": "2026-10-09T14:00:00Z",
    "private_details": "Keychain is a small silver Eiffel Tower.",
    "contact": "student@example.edu",
}

FOUND_BAG = {
    "type": "found",
    "description": "A navy school bag was left on a chair in the library.",
    "category": "bag",
    "color": "navy",
    "contact": "finder@example.edu",
}
