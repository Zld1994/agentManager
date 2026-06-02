"""
Performance Report Generation and Analysis

Generates comprehensive performance reports in multiple formats (HTML, Markdown)
with system information, metrics tables, charts, and recommendations.
"""

import json
import platform
import psutil
import statistics
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemInfo:
    """System information snapshot"""

    os_name: str
    os_version: str
    python_version: str
    processor_count: int
    total_memory_gb: float
    cpu_freq_ghz: float
    timestamp: str


class ReportGenerator:
    """
    Generates comprehensive performance reports in multiple formats.

    Supports:
    - HTML reports with charts and visualizations
    - Markdown reports with tables and formatting
    - Summary reports with key metrics
    """

    def __init__(self, output_dir: str = "./reports"):
        """
        Initialize report generator.

        Args:
            output_dir: Directory for generated reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.system_info = self._capture_system_info()

    def _capture_system_info(self) -> SystemInfo:
        """Capture current system information"""
        try:
            cpu_freq = psutil.cpu_freq()
            cpu_freq_ghz = cpu_freq.current / 1000 if cpu_freq else 0.0
        except Exception:
            cpu_freq_ghz = 0.0

        return SystemInfo(
            os_name=platform.system(),
            os_version=platform.release(),
            python_version=platform.python_version(),
            processor_count=psutil.cpu_count(),
            total_memory_gb=psutil.virtual_memory().total / (1024**3),
            cpu_freq_ghz=cpu_freq_ghz,
            timestamp=datetime.now().isoformat(),
        )

    def generate_html_report(
        self, metrics: List[Dict[str, Any]], output_path: Optional[str] = None
    ) -> Path:
        """
        Generate comprehensive HTML report with charts.

        Args:
            metrics: List of metric dictionaries from benchmark results
            output_path: Optional custom output path

        Returns:
            Path to generated HTML file
        """
        if output_path is None:
            output_path = (
                self.output_dir
                / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
        else:
            output_path = Path(output_path)

        html_content = self._build_html_report(metrics)

        with open(output_path, "w") as f:
            f.write(html_content)

        logger.info(f"Generated HTML report: {output_path}")
        return output_path

    def _build_html_report(self, metrics: List[Dict[str, Any]]) -> str:
        """Build HTML report content"""
        summary = self._calculate_summary(metrics)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Performance Benchmark Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .content {{
            padding: 40px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            color: #333;
            font-size: 1.8em;
            margin-bottom: 20px;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-card h3 {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .metric-card .value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .metric-card .unit {{
            font-size: 0.85em;
            opacity: 0.8;
        }}
        .chart-container {{
            position: relative;
            height: 400px;
            margin: 30px 0;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #e0e0e0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        th {{
            background: #f8f9fa;
            color: #333;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #667eea;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e0e0e0;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .system-info {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            margin-bottom: 20px;
        }}
        .system-info p {{
            margin: 8px 0;
            color: #555;
        }}
        .recommendations {{
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }}
        .recommendations h3 {{
            color: #2e7d32;
            margin-bottom: 10px;
        }}
        .recommendations ul {{
            margin-left: 20px;
            color: #555;
        }}
        .recommendations li {{
            margin: 8px 0;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
            border-top: 1px solid #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Performance Benchmark Report</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="content">
            <!-- System Information Section -->
            <div class="section">
                <h2>System Information</h2>
                <div class="system-info">
                    <p><strong>OS:</strong> {self.system_info.os_name}
                    {self.system_info.os_version}</p>
                    <p><strong>Python:</strong> {self.system_info.python_version}</p>
                    <p><strong>Processors:</strong> {self.system_info.processor_count}</p>
                    <p><strong>Total Memory:</strong> {self.system_info.total_memory_gb:.2f} GB</p>
                    <p><strong>CPU Frequency:</strong> {self.system_info.cpu_freq_ghz:.2f} GHz</p>
                </div>
            </div>

            <!-- Summary Metrics Section -->
            <div class="section">
                <h2>Summary Metrics</h2>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <h3>Avg Throughput</h3>
                        <div class="value">{summary.get('avg_throughput', 0):.2f}</div>
                        <div class="unit">tasks/sec</div>
                    </div>
                    <div class="metric-card">
                        <h3>Avg Latency P95</h3>
                        <div class="value">{summary.get('avg_latency_p95', 0):.2f}</div>
                        <div class="unit">ms</div>
                    </div>
                    <div class="metric-card">
                        <h3>Peak Memory</h3>
                        <div class="value">{summary.get('max_memory_peak', 0):.2f}</div>
                        <div class="unit">MB</div>
                    </div>
                    <div class="metric-card">
                        <h3>Peak CPU</h3>
                        <div class="value">{summary.get('max_cpu_peak', 0):.2f}</div>
                        <div class="unit">%</div>
                    </div>
                    <div class="metric-card">
                        <h3>Avg Error Rate</h3>
                        <div class="value">{summary.get('avg_error_rate', 0):.2f}</div>
                        <div class="unit">%</div>
                    </div>
                    <div class="metric-card">
                        <h3>Total Tests</h3>
                        <div class="value">{len(metrics)}</div>
                        <div class="unit">tests</div>
                    </div>
                </div>
            </div>

            <!-- Charts Section -->
            <div class="section">
                <h2>Performance Charts</h2>
                <div class="chart-container">
                    <canvas id="throughputChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="latencyChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="resourceChart"></canvas>
                </div>
            </div>

            <!-- Detailed Results Table -->
            <div class="section">
                <h2>Detailed Results</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Test Name</th>
                            <th>Throughput (tasks/sec)</th>
                            <th>Latency P95 (ms)</th>
                            <th>Memory Peak (MB)</th>
                            <th>CPU Peak (%)</th>
                            <th>Error Rate (%)</th>
                        </tr>
                    </thead>
                    <tbody>
"""

        for metric in metrics:
            html += f"""                        <tr>
                            <td>{metric.get('test_name', 'N/A')}</td>
                            <td>{metric.get('throughput', 0):.2f}</td>
                            <td>{metric.get('latency_p95', 0):.2f}</td>
                            <td>{metric.get('memory_peak', 0):.2f}</td>
                            <td>{metric.get('cpu_peak', 0):.2f}</td>
                            <td>{metric.get('error_rate', 0):.2f}</td>
                        </tr>
"""

        html += """                    </tbody>
                </table>
            </div>

            <!-- Recommendations Section -->
            <div class="section">
                <div class="recommendations">
                    <h3>Performance Recommendations</h3>
                    <ul>
"""

        recommendations = self._generate_recommendations(metrics, summary)
        for rec in recommendations:
            html += f"                        <li>{rec}</li>\n"

        html += (
            """                    </ul>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>Performance Benchmark Report | Generated on """
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + """</p>
        </div>
    </div>

    <script>
"""
        )

        html += self._generate_chart_scripts(metrics)
        html += """    </script>
</body>
</html>
"""
        return html

    def _calculate_summary(self, metrics: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate summary statistics"""
        if not metrics:
            return {}

        throughputs = [m.get("throughput", 0) for m in metrics if m.get("throughput", 0) > 0]
        latencies_p95 = [m.get("latency_p95", 0) for m in metrics if m.get("latency_p95", 0) > 0]
        memory_peaks = [m.get("memory_peak", 0) for m in metrics if m.get("memory_peak", 0) > 0]
        cpu_peaks = [m.get("cpu_peak", 0) for m in metrics if m.get("cpu_peak", 0) > 0]
        error_rates = [m.get("error_rate", 0) for m in metrics]

        return {
            "avg_throughput": statistics.mean(throughputs) if throughputs else 0,
            "min_throughput": min(throughputs) if throughputs else 0,
            "max_throughput": max(throughputs) if throughputs else 0,
            "avg_latency_p95": statistics.mean(latencies_p95) if latencies_p95 else 0,
            "max_latency_p95": max(latencies_p95) if latencies_p95 else 0,
            "avg_memory_peak": statistics.mean(memory_peaks) if memory_peaks else 0,
            "max_memory_peak": max(memory_peaks) if memory_peaks else 0,
            "avg_cpu_peak": statistics.mean(cpu_peaks) if cpu_peaks else 0,
            "max_cpu_peak": max(cpu_peaks) if cpu_peaks else 0,
            "avg_error_rate": statistics.mean(error_rates) if error_rates else 0,
        }

    def _generate_recommendations(
        self, metrics: List[Dict[str, Any]], summary: Dict[str, float]
    ) -> List[str]:
        """Generate performance recommendations based on metrics"""
        recommendations = []

        avg_error_rate = summary.get("avg_error_rate", 0)
        if avg_error_rate > 5:
            recommendations.append(
                f"High error rate detected ({avg_error_rate:.2f}%). "
                "Investigate failure causes and improve error handling."
            )

        max_latency = summary.get("max_latency_p95", 0)
        if max_latency > 1000:
            recommendations.append(
                f"High P95 latency detected ({max_latency:.2f}ms). "
                "Consider optimizing critical paths."
            )

        max_memory = summary.get("max_memory_peak", 0)
        if max_memory > 500:
            recommendations.append(
                f"High memory usage detected ({max_memory:.2f}MB). "
                "Review memory allocation patterns."
            )

        max_cpu = summary.get("max_cpu_peak", 0)
        if max_cpu > 80:
            recommendations.append(
                f"High CPU usage detected ({max_cpu:.2f}%). "
                "Consider parallelization or algorithm optimization."
            )

        if not recommendations:
            recommendations.append(
                "Performance metrics are within acceptable ranges. Continue monitoring."
            )

        return recommendations

    def _generate_chart_scripts(self, metrics: List[Dict[str, Any]]) -> str:
        """Generate Chart.js scripts for visualizations"""
        test_names = [m.get("test_name", "Test") for m in metrics]
        throughputs = [m.get("throughput", 0) for m in metrics]
        latencies = [m.get("latency_p95", 0) for m in metrics]
        memory_peaks = [m.get("memory_peak", 0) for m in metrics]
        cpu_peaks = [m.get("cpu_peak", 0) for m in metrics]

        script = f"""
        const ctx1 = document.getElementById('throughputChart').getContext('2d');
        new Chart(ctx1, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(test_names)},
                datasets: [{{
                    label: 'Throughput (tasks/sec)',
                    data: {json.dumps(throughputs)},
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Throughput Comparison'
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});

        const ctx2 = document.getElementById('latencyChart').getContext('2d');
        new Chart(ctx2, {{
            type: 'line',
            data: {{
                labels: {json.dumps(test_names)},
                datasets: [{{
                    label: 'Latency P95 (ms)',
                    data: {json.dumps(latencies)},
                    borderColor: 'rgba(118, 75, 162, 1)',
                    backgroundColor: 'rgba(118, 75, 162, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Latency P95 Trend'
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});

        const ctx3 = document.getElementById('resourceChart').getContext('2d');
        new Chart(ctx3, {{
            type: 'radar',
            data: {{
                labels: {json.dumps(test_names)},
                datasets: [
                    {{
                        label: 'Memory Peak (MB)',
                        data: {json.dumps(memory_peaks)},
                        borderColor: 'rgba(76, 175, 80, 1)',
                        backgroundColor: 'rgba(76, 175, 80, 0.2)',
                        borderWidth: 2
                    }},
                    {{
                        label: 'CPU Peak (%)',
                        data: {json.dumps(cpu_peaks)},
                        borderColor: 'rgba(255, 152, 0, 1)',
                        backgroundColor: 'rgba(255, 152, 0, 0.2)',
                        borderWidth: 2
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Resource Usage'
                    }}
                }},
                scales: {{
                    r: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
"""
        return script

    def generate_markdown_report(
        self, metrics: List[Dict[str, Any]], output_path: Optional[str] = None
    ) -> Path:
        """
        Generate Markdown report with tables and formatting.

        Args:
            metrics: List of metric dictionaries from benchmark results
            output_path: Optional custom output path

        Returns:
            Path to generated Markdown file
        """
        if output_path is None:
            output_path = (
                self.output_dir
                / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            )
        else:
            output_path = Path(output_path)

        md_content = self._build_markdown_report(metrics)

        with open(output_path, "w") as f:
            f.write(md_content)

        logger.info(f"Generated Markdown report: {output_path}")
        return output_path

    def _build_markdown_report(self, metrics: List[Dict[str, Any]]) -> str:
        """Build Markdown report content"""
        summary = self._calculate_summary(metrics)

        md = f"""# Performance Benchmark Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## System Information

| Property | Value |
|----------|-------|
| OS | {self.system_info.os_name} {self.system_info.os_version} |
| Python | {self.system_info.python_version} |
| Processors | {self.system_info.processor_count} |
| Total Memory | {self.system_info.total_memory_gb:.2f} GB |
| CPU Frequency | {self.system_info.cpu_freq_ghz:.2f} GHz |

## Summary Metrics

| Metric | Value | Unit |
|--------|-------|------|
| Average Throughput | {summary.get('avg_throughput', 0):.2f} | tasks/sec |
| Min Throughput | {summary.get('min_throughput', 0):.2f} | tasks/sec |
| Max Throughput | {summary.get('max_throughput', 0):.2f} | tasks/sec |
| Average Latency P95 | {summary.get('avg_latency_p95', 0):.2f} | ms |
| Max Latency P95 | {summary.get('max_latency_p95', 0):.2f} | ms |
| Average Memory Peak | {summary.get('avg_memory_peak', 0):.2f} | MB |
| Max Memory Peak | {summary.get('max_memory_peak', 0):.2f} | MB |
| Average CPU Peak | {summary.get('avg_cpu_peak', 0):.2f} | % |
| Max CPU Peak | {summary.get('max_cpu_peak', 0):.2f} | % |
| Average Error Rate | {summary.get('avg_error_rate', 0):.2f} | % |

## Detailed Results

"""
        md += (
            "| Test Name | Throughput (tasks/sec) | Latency P95 (ms) | "
            "Memory Peak (MB) | CPU Peak (%) | Error Rate (%) |\n"
            "|-----------|------------------------|------------------|"
            "------------------|--------------|----------------|\n"
        )

        for metric in metrics:
            md += (
                f"| {metric.get('test_name', 'N/A')} | "
                f"{metric.get('throughput', 0):.2f} | "
                f"{metric.get('latency_p95', 0):.2f} | "
                f"{metric.get('memory_peak', 0):.2f} | "
                f"{metric.get('cpu_peak', 0):.2f} | "
                f"{metric.get('error_rate', 0):.2f} |\n"
            )

        md += "\n## Performance Recommendations\n\n"

        recommendations = self._generate_recommendations(metrics, summary)
        for i, rec in enumerate(recommendations, 1):
            md += f"{i}. {rec}\n"

        md += "\n## Latency Distribution\n\n"
        md += "| Test Name | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) |\n"
        md += "|-----------|----------|----------|----------|----------|----------|\n"

        for metric in metrics:
            md += (
                f"| {metric.get('test_name', 'N/A')} | "
                f"{metric.get('latency_min', 0):.2f} | "
                f"{metric.get('latency_p50', 0):.2f} | "
                f"{metric.get('latency_p95', 0):.2f} | "
                f"{metric.get('latency_p99', 0):.2f} | "
                f"{metric.get('latency_max', 0):.2f} |\n"
            )

        md += "\n## Resource Usage Summary\n\n"
        md += "| Test Name | Memory Avg (MB) | Memory Peak (MB) | CPU Avg (%) | CPU Peak (%) |\n"
        md += "|-----------|-----------------|------------------|-------------|---------------|\n"

        for metric in metrics:
            md += (
                f"| {metric.get('test_name', 'N/A')} | "
                f"{metric.get('memory_avg', 0):.2f} | "
                f"{metric.get('memory_peak', 0):.2f} | "
                f"{metric.get('cpu_avg', 0):.2f} | "
                f"{metric.get('cpu_peak', 0):.2f} |\n"
            )

        md += "\n## Test Environment Details\n\n"
        md += f"- **Report Generated:** {datetime.now().isoformat()}\n"
        md += f"- **Total Tests:** {len(metrics)}\n"
        md += f"- **System:** {self.system_info.os_name} {self.system_info.os_version}\n"
        md += f"- **Python Version:** {self.system_info.python_version}\n"

        return md

    def generate_summary_report(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate summary report as dictionary.

        Args:
            metrics: List of metric dictionaries from benchmark results

        Returns:
            Dictionary containing summary report
        """
        summary = self._calculate_summary(metrics)

        return {
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "os": f"{self.system_info.os_name} {self.system_info.os_version}",
                "python": self.system_info.python_version,
                "processors": self.system_info.processor_count,
                "memory_gb": self.system_info.total_memory_gb,
                "cpu_freq_ghz": self.system_info.cpu_freq_ghz,
            },
            "summary_metrics": summary,
            "test_count": len(metrics),
            "tests": metrics,
            "recommendations": self._generate_recommendations(metrics, summary),
        }
