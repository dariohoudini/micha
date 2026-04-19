"""
Run from your MICHA project root:
    python scan_imports.py
"""
import os, re, sys

APPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps')

if not os.path.exists(APPS_DIR):
    print("ERROR: Run from your MICHA project root")
    sys.exit(1)

problems = []
clean = []

# Known views that come from third-party packages, not .views
THIRD_PARTY_VIEWS = {
    'TokenRefreshView', 'TokenObtainPairView', 'TokenVerifyView',
    'LoginView', 'LogoutView',
}

for app in sorted(os.listdir(APPS_DIR)):
    app_path = os.path.join(APPS_DIR, app)
    if not os.path.isdir(app_path):
        continue

    urls_path  = os.path.join(app_path, 'urls.py')
    views_path = os.path.join(app_path, 'views.py')
    models_path = os.path.join(app_path, 'models.py')
    app_problems = []

    # ── urls.py → views.py ────────────────────────────────────────────────────
    if os.path.exists(urls_path) and os.path.exists(views_path):
        urls_content  = open(urls_path).read()
        views_content = open(views_path).read()

        # Only look at names imported from .views (not third-party)
        dot_view_imports = set()
        for m in re.finditer(r'from \.views import\s*\(?([^)]+)\)?', urls_content, re.DOTALL):
            for name in re.findall(r'\b([A-Z][A-Za-z]+)\b', m.group(1)):
                dot_view_imports.add(name)

        defined = set(re.findall(r'^class ([A-Z][A-Za-z]+)', views_content, re.MULTILINE))
        defined |= set(re.findall(r'^def ([a-z][A-Za-z]+)', views_content, re.MULTILINE))

        missing = dot_view_imports - defined - THIRD_PARTY_VIEWS
        if missing:
            app_problems.append(f"  urls.py imports MISSING views: {sorted(missing)}")

    elif os.path.exists(urls_path) and not os.path.exists(views_path):
        app_problems.append("  urls.py exists but views.py MISSING")

    # ── views.py → models.py ──────────────────────────────────────────────────
    if os.path.exists(views_path) and os.path.exists(models_path):
        views_content  = open(views_path).read()
        models_content = open(models_path).read()

        imported_models = set()
        for m in re.finditer(r'from \.models import\s*\(?([^)]+)\)?', views_content, re.DOTALL):
            for name in re.findall(r'\b([A-Z][A-Za-z]+)\b', m.group(1)):
                imported_models.add(name)

        defined_models = set(re.findall(r'^class ([A-Z][A-Za-z]+)', models_content, re.MULTILINE))
        missing_models = imported_models - defined_models
        if missing_models:
            app_problems.append(f"  views.py imports MISSING models: {sorted(missing_models)}")

    if app_problems:
        problems.append((app, app_problems))
    else:
        clean.append(app)

print(f"\n{'='*60}\nMICHA Import Scanner\n{'='*60}\n")

if problems:
    print(f"❌ Found problems in {len(problems)} apps:\n")
    for app, issues in problems:
        print(f"apps/{app}/")
        for issue in issues:
            print(issue)
        print()
else:
    print("✅ All apps are clean — no broken imports found!\n")

print(f"✅ Clean ({len(clean)}): {', '.join(clean)}")
if problems:
    print(f"❌ Broken ({len(problems)}): {', '.join(a for a,_ in problems)}")
