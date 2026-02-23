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
            
            # Check for security issues
            no_policy = [login for login in security['login_audit'] if login.get('is_policy_checked') == False]
            if no_policy:
                print(f"⚠️  WARNING: {len(no_policy)} logins without password policy")
        
        if 'permissions_audit' in security:
            print(f"Permissions Audit: {len(security['permissions_audit'])} permission entries")
        
        if 'security_config' in security:
            security_configs = security['security_config']
            if isinstance(security_configs, list):
                print(f"Security Configuration: {len(security_configs)} settings")
                dangerous = [config for config in security_configs if config.get('value_in_use') == 1 and config.get('name') in ['xp_cmdshell', 'Ad Hoc Distributed Queries']]
                if dangerous:
                    print(f"⚠️  WARNING: {len(dangerous)} dangerous configurations enabled")
                    for config in dangerous:
                        print(f"   - {config.get('name')}: {config.get('description')}")
            else:
                print(f"Security Configuration: {security_configs}") # Print error message if it's not a list
        
        # Performance Metrics
        print("\n--- Performance Metrics ---")
        performance = results['performance_metrics']
        
        wait_stats_data = performance.get('wait_stats')
        if isinstance(wait_stats_data, list) and wait_stats_data:
            print(f"Wait Statistics: {len(wait_stats_data)} wait types")
            top_wait = wait_stats_data[0]
            print(f"Top Wait: {top_wait.get('wait_type')} ({top_wait.get('wait_percentage')}%)")
        elif wait_stats_data:
            print(f"Wait Statistics: {wait_stats_data}") # Print error message if it's not a list
        
        memory_usage_data = performance.get('memory_usage')
        if isinstance(memory_usage_data, list) and memory_usage_data:
            memory = memory_usage_data[0]
            print(f"Memory Usage: {memory.get('memory_utilization_percent')}% utilized")
            print(f"Physical Memory: {memory.get('physical_memory_mb')} MB")
        elif memory_usage_data:
            print(f"Memory Usage: {memory_usage_data}") # Print error message if it's not a list
        
        cpu_stats_data = performance.get('cpu_stats')
        if isinstance(cpu_stats_data, list) and cpu_stats_data:
            cpu = cpu_stats_data[0]
            print(f"CPU Count: {cpu.get('cpu_count')}")
            print(f"Hyperthread Ratio: {cpu.get('hyperthread_ratio')}")
        elif cpu_stats_data:
            print(f"CPU Statistics: {cpu_stats_data}") # Print error message if it's not a list
        
        # Risk Assessment
        print("\n--- Risk Assessment ---")
        risk = results['risk_assessment']
        print(f"Overall Risk Score: {risk['overall_risk_score']}/100")
        print(f"Risk Level: {risk['risk_level']}")
        
        if risk['risk_factors']:
            print("Risk Factors:")
            for factor in risk['risk_factors']:
                print(f"  - {factor}")
        
        # Profile-specific metrics
        if 'profile_specific_metrics' in risk:
            profile_metrics = risk['profile_specific_metrics']
            print(f"Profile Compliance: {profile_metrics['compliance_status']}")
        
        # Recommendations
        print("\n--- Recommendations ---")
        recommendations = results['recommendations']
        if recommendations:
            print(f"Total Recommendations: {len(recommendations)}")
            
            # Group by priority
            critical = [r for r in recommendations if r['priority'] == 'CRITICAL']
            high = [r for r in recommendations if r['priority'] == 'HIGH']
            medium = [r for r in recommendations if r['priority'] == 'MEDIUM']
            
            if critical:
                print(f"\n🚨 CRITICAL ({len(critical)}):")
                for rec in critical:
                    print(f"   - {rec['issue']}")
                    print(f"     Action: {rec['recommendation']}")
            
            if high:
                print(f"\n⚠️  HIGH ({len(high)}):")
                for rec in high:
                    print(f"   - {rec['issue']}")
                    print(f"     Action: {rec['recommendation']}")
            
            if medium:
                print(f"\nℹ️  MEDIUM ({len(medium)}):")
                for rec in medium:
                    print(f"   - {rec['issue']}")
        
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