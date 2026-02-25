#!/usr/bin/env python3
"""
Test script to demonstrate db_sql2019_show_top_queries with readonly alias.
This simulates the MCP client request: "using sqlserver_readonly, call db_sql2019_show_top_queries(database='USGISPRO_800') and display results"
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add the current directory to Python path
sys.path.append('.')

# Import the MCP server and tools
from server import db_sql2019_show_top_queries, mcp

async def test_readonly_queries():
    """Test the db_sql2019_show_top_queries function with readonly database"""
    
    print("🧪 Testing db_sql2019_show_top_queries with readonly alias")
    print("=" * 60)
    
    # Test database name from environment (fallback to TEST_DB)
    test_database = os.environ.get("DB_NAME") or os.environ.get("TEST_DB_NAME") or "TEST_DB"
    
    try:
        print(f"📊 Analyzing Query Store for database: {test_database}")
        print(f"⏰ Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Call the function directly (this simulates the MCP tool call)
        result = db_sql2019_show_top_queries(test_database)
        if asyncio.iscoroutine(result):
            result = await result
        
        print("✅ Query Store analysis completed successfully!")
        print()
        
        # Display the results in a formatted way
        print("📈 ANALYSIS RESULTS:")
        print("-" * 40)
        
        # Check if Query Store is enabled
        if result.get('query_store_enabled', False):
            print(f"✅ Query Store is ENABLED for {test_database}")
            print(f"📊 Total queries analyzed: {result.get('total_queries', 0):,}")
            
            # Display analysis period
            analysis_period = result.get('analysis_period', {})
            if analysis_period:
                print(f"📅 Analysis period: {analysis_period.get('earliest_data', 'N/A')} to {analysis_period.get('latest_data', 'N/A')}")
                print(f"📊 Days covered: {analysis_period.get('days_covered', 0)}")
            
            print()
            
            # Display query categories
            categories = [
                ('long_running_queries', 'Long Running Queries (>1 second)'),
                ('regressed_queries', 'Regressed Queries'),
                ('high_cpu_queries', 'High CPU Queries'),
                ('high_io_queries', 'High I/O Queries'),
                ('high_execution_queries', 'High Execution Count Queries')
            ]
            
            for category_key, category_name in categories:
                queries = result.get(category_key, [])
                print(f"🔍 {category_name}: {len(queries)} found")
                if queries:
                    print(f"   Top issues:")
                    for i, query in enumerate(queries[:3], 1):  # Show top 3
                        query_text = query.get('query_text', 'N/A')[:100] + "..." if len(query.get('query_text', '')) > 100 else query.get('query_text', 'N/A')
                        print(f"   {i}. Query ID {query.get('query_id', 'N/A')}: {query_text}")
                        # Show specific metrics based on category
                        if category_key == 'long_running_queries':
                            print(f"      ⏱️  Avg duration: {query.get('avg_duration_ms', 0):.1f}ms")
                        elif category_key == 'regressed_queries':
                            regression = query.get('regression_percent')
                            if regression is not None:
                                print(f"      📈 Regression: {regression:.1f}%")
                        elif category_key == 'high_cpu_queries':
                            print(f"      💻 Avg CPU: {query.get('avg_cpu_ms', 0):.1f}ms")
                        elif category_key == 'high_io_queries':
                            print(f"      💾 Avg logical reads: {query.get('avg_logical_io_reads', 0):,}")
                        elif category_key == 'high_execution_queries':
                            print(f"      🔢 Executions: {query.get('executions', 0):,}")
                    if len(queries) > 3:
                        print(f"   ... and {len(queries) - 3} more")
                print()
            
            # Display recommendations
            recommendations = result.get('recommendations', [])
            if recommendations:
                print("💡 RECOMMENDATIONS:")
                print("-" * 40)
                for i, rec in enumerate(recommendations[:5], 1):  # Show top 5 recommendations
                    priority = (rec.get('priority') or 'N/A').upper()
                    typ = (rec.get('type') or 'N/A')
                    print(f"{i}. [{priority}] {typ}")
                    print(f"   Issue: {rec.get('issue', 'N/A')}")
                    print(f"   Recommendation: {rec.get('recommendation', 'N/A')}")
                    print()
            
        else:
            print(f"❌ Query Store is NOT ENABLED for {test_database}")
            print("💡 To enable Query Store, run: ALTER DATABASE [database_name] SET QUERY_STORE = ON")
        
        # Display any errors
        if 'error' in result:
            print(f"⚠️  Error: {result['error']}")
        
        print()
        print("🎯 Test completed successfully!")

        # Minimal assertions for contract
        assert result is not None, "Result should not be None"
        assert result.get('query_store_enabled') is True, "Query Store should be enabled"
        assert isinstance(result.get('total_queries', 0), int), "total_queries should be int"
        assert isinstance(result.get('long_running_queries', []), list), "long_running_queries should be a list"

        # Save results only if TEST_SAVE_RESULTS env is set
        import tempfile
        save_results = os.environ.get('TEST_SAVE_RESULTS') == '1'
        if save_results:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json', prefix='readonly_results_', dir='.') as f:
                json.dump(result, f, indent=2, default=str)
                temp_path = f.name
            print(f"📋 Full results saved to: {temp_path}")

        return result
        
    except ValueError as e:
        print(f"❌ Validation Error: {e}")
        print("💡 This might indicate an invalid database name or configuration issue.")
        return None
        
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        print("💡 Check the server logs for more details.")
        return None

if __name__ == "__main__":
    print("🔧 MCP SQL Server - Readonly Query Store Analysis Test")
    print("This test simulates: 'using sqlserver_readonly, call db_sql2019_show_top_queries(database='USGISPRO_800')'")
    print()
    
    # Check if environment is configured
    required_vars = ['DB_SERVER', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print("💡 Please set up your .env file or export the required variables.")
        print("📋 Required variables: DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD")
        sys.exit(1)
    
    # Run the test
    result = asyncio.run(test_readonly_queries())
    
    if result:
        print("\n✅ Test passed! The readonly queries function is working correctly.")
    else:
        print("\n❌ Test failed. Please check the error messages above.")
        sys.exit(1)
