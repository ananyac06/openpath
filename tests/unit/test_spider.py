"""Unit tests for career page ATS link detection."""

from openpath.connectors.spider import detect_ats_links


def test_detect_ats_links() -> None:
    html_sample = """
    <html>
        <body>
            <h1>Careers at Fintech Corp</h1>
            <a href="https://boards.greenhouse.io/fintechcorp/jobs/1234">View Openings on Greenhouse</a>
            <a href="https://jobs.lever.co/fintechcorp">Lever Board</a>
            <a href="https://jobs.ashbyhq.com/fintechcorp">Ashby Board</a>
        </body>
    </html>
    """

    detected = detect_ats_links(html_sample)
    providers = {d.provider: d.board_token for d in detected}

    assert providers.get("greenhouse") == "fintechcorp"
    assert providers.get("lever") == "fintechcorp"
    assert providers.get("ashby") == "fintechcorp"
