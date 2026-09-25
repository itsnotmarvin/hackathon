from app.database import supabase


# 1. Create startup
startup = {
    "name": "Test Robotics",
    "legal_name": "Test Robotics LLC",
    "website": "https://example.com",
    "city": "Newark",
    "state": "NJ",
    "description": "Test startup for 1435 Capital"
}

startup_response = (
    supabase
    .table("startups")
    .insert(startup)
    .execute()
)

startup_data = startup_response.data[0]

print("Startup created:")
print(startup_data)


# 2. Get the startup ID
startup_id = startup_data["id"]


# 3. Add founder
founder = {
    "startup_id": startup_id,
    "name": "John Smith",
    "title": "Co-Founder & CEO"
}

founder_response = (
    supabase
    .table("founders")
    .insert(founder)
    .execute()
)

print("\nFounder created:")
print(founder_response.data)