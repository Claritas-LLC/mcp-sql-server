#!/usr/bin/env python3
"""Test script for db_sql2019_db_sec_perf_metrics function."""

import json
import sys
import os

# Add the current directory to Python path to import server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import db_sql2019_db_sec_perf_metrics

def test_sec_perf_metrics():
    """Test the security and performance metrics function."""
    print("Testing db_sql2019_db_sec_perf_metrics with profile='oltp'...")
    
    try:
        # Test with OLTP profile
        results = db_sql2019_db_sec_perf_metrics(profile='oltp')
        
        print("\n=== Security and Performance Metrics Analysis ===")
        print(f"Profile: {results['profile']}")
        print(f"Analysis Timestamp: {results['analysis_timestamp']}")
        
        if 'error' in results:
            print(f"\n❌ ERROR: {results['error']}")
            if 'recommendations' in results:
                print("\n--- Recommendations (from error response) ---")
                for rec in results['recommendations']:
                    print(f"  - {rec['issue']}: {rec['recommendation']}")
            return False
        
        # Security Assessment
        print("\n--- Security Assessment ---")
        security = results['security_assessment']
        
        if 'login_audit' in security:
            print(f"Login Audit: {len(security['login_audit'])} logins found")
            active_logins = [login for login in security['login_audit'] if login.get('is_disabled') == False]
            print(f"Active Logins: {len(active_logins)}")
        
        if 'permissions_audit' in security:
            print(f"Permissions Audit: {len(security['permissions_audit'])} permission entries")
        
        # Performance Metrics
        print("\n--- Performance Metrics ---")
        performance = results['performance_metrics']
        
        # Risk Assessment
        print("\n--- Risk Assessment ---")
        risk = results['risk_assessment']
        print(f"Overall Risk Score: {risk['overall_risk_score']}/100")
        print(f"Risk Level: {risk['risk_level']}")
        
        # Recommendations
        print("\n--- Recommendations ---")
        recommendations = results['recommendations']
        if recommendations:
            print(f"Total Recommendations: {len(recommendations)}")
        
        # Save results to file
        output_file = "test_sec_perf_metrics_results.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n✅ Test completed successfully!")
        print(f"Results saved to: {output_file}")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_sec_perf_metrics()
    sys.exit(0 if success else 1)
