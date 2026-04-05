"""
SpiderFoot OSINT Client

Programmatic wrapper around the local SpiderFoot installation to run OSINT
scans on Twitter usernames or URLs to enrich bot-scoring heuristics.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SpiderfootClient:
    """Wrapper to execute SpiderFoot CLI and parse results."""

    def __init__(self, spiderfoot_dir: str = "./spiderfoot"):
        self.sf_dir = Path(spiderfoot_dir).absolute()
        self.sf_executable = self.sf_dir / "sf.py"
        
        if not self.sf_executable.exists():
            logger.warning(
                f"SpiderFoot not found at {self.sf_executable}. "
                "OSINT enrichment runs will be skipped."
            )
            self.available = False
        else:
            self.available = True

    def scan_target(self, target: str, modules: str = "sfp_accounts") -> float:
        """
        Run a targeted SpiderFoot scan and return an OSINT risk score (0.0 to 1.0).
        
        Args:
            target: Username or URL to scan.
            modules: Comma-separated list of SpiderFoot modules to run.
                     e.g. 'sfp_accounts,sfp_spider'
        
        Returns:
            Risk score: 1.0 = highly suspicious (associated with multiple flags),
                        0.0 = clean or unresolved.
        """
        if not self.available:
            return 0.0

        logger.info(f"Running SpiderFoot OSINT scan on target: {target} (Modules: {modules})...")
        
        try:
            # Command: python sf.py -s <TARGET> -m <MODULES> -q -o json
            cmd = [
                "python", str(self.sf_executable),
                "-s", target,
                "-m", modules,
                "-q",          # No verbose logging
                "-o", "json",  # Output format JSON
            ]
            try:
                # Command: python sf.py -s <TARGET> -m <MODULES> -q -o json
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.sf_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                try:
                    stdout, stderr = proc.communicate(timeout=10)  # slightly longer grace
                    if proc.returncode != 0:
                        logger.error(f"SpiderFoot CLI failed ({proc.returncode}): {stderr}")
                        return 0.2  # minor fallback
                except subprocess.TimeoutExpired:
                    proc.kill()
                    logger.warning(f"SpiderFoot timed out after 10s for {target}. Using fallback score.")
                    return 0.65  # Fallback score if we can't get data fast enough

                output = stdout.strip()
            except Exception as e:
                logger.error(f"Failed to spawn SpiderFoot process: {e}")
                return 0.1
            if not output:
                return 0.0

            # Parse JSON output
            # sf.py JSON output is a list of events.
            events = []
            for line in output.split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    continue

            return self._calculate_risk_score(events)

        except Exception as e:
            logger.error(f"Failed to execute SpiderFoot for {target}: {e}")
            return 0.0

    def _calculate_risk_score(self, events: list) -> float:
        """Calculate a risk score [0, 1] based on OSINT events returned."""
        if not events:
            return 0.0
            
        risk_score = 0.0
        
        for event in events:
            event_type = event.get("type", "")
            
            # Known malicious IP or domain
            if event_type in ["MALICIOUS_IP", "MALICIOUS_HOST", "MALICIOUS_NETBLOCK"]:
                risk_score += 0.8
                
            # Suspicious associations (e.g. pastebin leaks, blocklists)
            elif event_type in ["LEAKSITE_CONTENT", "BLACKLISTED_COHOST", "SPAM_ADDRESS"]:
                risk_score += 0.5
                
            # Found on multiple random obscure sites (bot cross-posting)
            elif event_type in ["ACCOUNT_EXTERNAL_OWNED"]:
                risk_score += 0.05
                
        # Cap at 1.0
        return min(risk_score, 1.0)
