#!/usr/bin/env python3

import asyncio
import json
import sys
import os

# Add the current directory to the path so we can import from server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import db_sql2019_check_fragmentation

async def test_fragmentation_check():
    """Test the new fragmentation check function"""
    try:
        print("Testing db_sql2019_check_fragmentation function...")
        print("Calling function with: database='USGISPRO_800', min_fragmentation=5, min_page_count=100")

        # Call the function
        result = db_sql2019_check_fragmentation(
            database_name='USGISPRO_800',
            min_fragmentation=15.0,
            min_page_count=100,
            include_recommendations=True
        )

        print("Function executed successfully!")
        print(f"Result type: {type(result)}")
        print(f"Result keys: {list(result.keys())}")
        
        # Print summary
        if 'fragmentation_summary' in result:
            summary = result['fragmentation_summary']
            print(f"\nFragmentation Summary:")
            print(f"- Severe fragmentation: {summary['severe_fragmentation']}")
            print(f"- High fragmentation: {summary['high_fragmentation']}")
            print(f"- Medium fragmentation: {summary['medium_fragmentation']}")
            print(f"- Low fragmentation: {summary['low_fragmentation']}")
        
        if 'total_fragmented_indexes' in result:
            print(f"\nTotal fragmented indexes: {result['total_fragmented_indexes']}")
        
        # Print top fragmented indexes
        if 'top_fragmented_indexes' in result and result['top_fragmented_indexes']:
            print(f"\nTop {len(result['top_fragmented_indexes'])} fragmented indexes:")
            for idx in result['top_fragmented_indexes'][:5]:  # Show top 5
                print(f"- {idx['SchemaName']}.{idx['TableName']}.{idx['IndexName']}: {idx['FragmentationPercent']}% ({idx['Severity']})")
        
        # Print fix commands
        if 'fix_commands' in result and result['fix_commands']:
            print(f"\nSample fix commands ({len(result['fix_commands'])} total):")
            for cmd in result['fix_commands'][:3]:  # Show first 3 commands
                print(f"\nTable: {cmd['TableName']}")
                print(f"Index: {cmd['IndexName']}")
                print(f"Fragmentation: {cmd['Fragmentation']}%")
                print(f"Command: {cmd['Command']}")
                print(f"Estimated Time: {cmd['EstimatedTime']}")
                print(f"Impact: {cmd['Impact']}")
        
        # Print maintenance plan
        if 'maintenance_plan' in result and result['maintenance_plan']:
            print(f"\nMaintenance Plan:")
            for phase in result['maintenance_plan']:
                print(f"- {phase['Phase']}: {phase['Indexes']} indexes ({phase['Priority']})")
        
        # Print recommendations
        if 'recommendations' in result and result['recommendations']:
            print(f"\nRecommendations:")
            for rec in result['recommendations']:
                print(f"- [{rec['category']}] {rec['message']}")
                print(f"  Action: {rec['action']}")

        return result

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_fragmentation_check())