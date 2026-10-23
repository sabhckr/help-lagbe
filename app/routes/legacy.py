"""Old addresses from earlier versions. They redirect so existing links keep working."""

from flask import Blueprint, abort, redirect, url_for

legacy_bp = Blueprint("legacy", __name__)

REDIRECTS: dict[str, tuple[str, dict[str, str]]] = {
    "/submit": ("report.new", {}),
    "/login": ("auth.login", {}),
    "/register": ("auth.register", {}),
    "/logout": ("auth.logout", {}),
    "/dashboard": ("workspace.home", {}),
    "/editorial": ("workspace.publications", {}),
    "/logs": ("workspace.audit", {}),
    "/get-help": ("public.help_page", {}),
    "/live-support": ("public.help_page", {}),
    "/report-wrongdoing": ("report.new", {}),
    "/legal-help": ("public.safety", {}),
    "/digital-safety": ("public.safety", {}),
    "/safeguarding": ("public.about", {}),
    "/editorial-policy": ("public.about", {}),
    "/awareness": ("public.stories", {}),
    "/investigations": ("public.stories", {}),
    "/corrections": ("public.stories", {}),
    "/complaints": ("public.contact", {}),
    "/accessibility": ("public.contact", {}),
}


def _make(path, endpoint, extra):
    def view():
        return redirect(url_for(endpoint, **extra), code=301)

    view.__name__ = "legacy_" + path.strip("/").replace("-", "_")
    return view


for _path, (_endpoint, _extra) in REDIRECTS.items():
    legacy_bp.add_url_rule(_path, view_func=_make(_path, _endpoint, _extra))


@legacy_bp.route("/p/<slug>")
def old_publication(slug: str):
    return redirect(url_for("public.story", slug=slug), code=301)


@legacy_bp.route("/case/<int:case_id>")
def old_case(case_id: int):
    abort(404)
