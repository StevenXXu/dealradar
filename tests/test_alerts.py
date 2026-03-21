from src.commander.alerts import check_serpapi, send_raise_alert_email
from unittest.mock import patch, MagicMock

def test_serpapi_returns_true_with_news(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "fake-key")
    import src.commander.alerts as alerts_module
    alerts_module.SERPAPI_API_KEY = "fake-key"
    with patch("src.commander.alerts.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "organic_results": [{"title": "Startup Raises $10M Series A"}]
        }
        result = check_serpapi("https://startup.co", "StartupCo")
        assert result == True

def test_serpapi_returns_false_without_news():
    with patch("src.commander.alerts.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"organic_results": []}
        result = check_serpapi("https://startup.co", "StartupCo")
        assert result == False

def test_serpapi_warns_and_returns_false_without_api_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with patch("builtins.print") as mock_print:
        result = check_serpapi("https://startup.co", "StartupCo")
        assert result == False

def test_send_raise_alert_email_uses_sendgrid(monkeypatch):
    monkeypatch.setenv("SENDGRID_API_KEY", "fake-key")
    monkeypatch.setenv("ALERT_EMAIL", "test@example.com")
    import src.commander.alerts as alerts_module
    alerts_module.HAS_SENDGRID = True
    alerts_module.ALERT_EMAIL = "test@example.com"
    with patch("src.commander.alerts.sendgrid.SendGridAPIClient") as mock_sg_cls:
        mock_sg = MagicMock()
        mock_sg.send.return_value = MagicMock(status_code=202)
        mock_sg_cls.return_value = mock_sg
        result = send_raise_alert_email({
            "company_name": "TestCo",
            "last_raise_amount": "$5M",
            "vc_source": "Blackbird",
            "signal_score": 30,
            "one_liner": "AI startup",
            "domain": "https://test.co",
            "current_date": "March 2026",
        })
        assert result == True
        mock_sg.send.assert_called_once()
