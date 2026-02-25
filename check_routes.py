"""
Route Checker - Verify all routes are registered
Run this AFTER replacing app.py to verify routes exist
"""

try:
    from app import app
    
    print("=" * 70)
    print("FLASK ROUTE VERIFICATION")
    print("=" * 70)
    
    # Get all routes
    all_routes = []
    for rule in app.url_map.iter_rules():
        all_routes.append({
            'route': rule.rule,
            'methods': ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        })
    
    # Sort by route
    all_routes.sort(key=lambda x: x['route'])
    
    print("\n📋 ALL REGISTERED ROUTES:")
    print("-" * 70)
    for r in all_routes:
        print(f"{r['route']:45s} | {r['methods']}")
    
    # Check critical routes for attendance system
    print("\n" + "=" * 70)
    print("🔍 CRITICAL ROUTE CHECK")
    print("=" * 70)
    
    critical_routes = {
        '/records': 'View attendance records',
        '/edit/<int:record_id>': 'Edit attendance record',
        '/delete/<int:record_id>': 'Delete attendance record',
        '/download/attendance': 'Download CSV (NEW!)',
        '/update': 'Update record after edit',
        '/dashboard': 'Camera dashboard',
        '/faculty/schedule': 'Faculty schedule page'
    }
    
    for route, description in critical_routes.items():
        # Check if route exists (handle parameterized routes)
        route_pattern = route.replace('<int:record_id>', '<int>')
        exists = any(route in str(rule.rule) or route_pattern in str(rule.rule) 
                    for rule in app.url_map.iter_rules())
        
        status = "✅ FOUND" if exists else "❌ MISSING"
        print(f"{status} | {route:35s} | {description}")
    
    print("\n" + "=" * 70)
    print("ROUTE COUNT:", len(all_routes))
    print("=" * 70)
    
    # Check for download route specifically
    has_download = any('/download/attendance' in str(rule.rule) 
                      for rule in app.url_map.iter_rules())
    
    if has_download:
        print("\n✅ SUCCESS: Download route is registered!")
        print("   You should now be able to download CSV files.")
    else:
        print("\n❌ ERROR: Download route NOT found!")
        print("   Make sure you replaced app.py with the NEW version.")
        print("   The route should be around line 211 in app.py")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("1. If all critical routes show ✅ FOUND - restart Flask")
    print("2. If any route shows ❌ MISSING - check your app.py file")
    print("3. After restart, test in browser: http://127.0.0.1:5000/records")
    print("=" * 70)
    
except ImportError as e:
    print("❌ ERROR: Could not import app.py")
    print(f"   Error: {e}")
    print("\n   Make sure you're running this from your project directory")
    print("   and that app.py exists in the same folder.")
except Exception as e:
    print(f"❌ ERROR: {e}")
    print("\n   Something went wrong. Check that app.py is valid Python code.")
