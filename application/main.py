"""
Main CLI entry point for the contract analysis system.
"""
import sys
import argparse
from pathlib import Path
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.logging_config import setup_logging
from application.workflows.stage1_discovery import run_stage1_discovery


def main():
    """
    Main CLI entry point.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Contract Analysis System - Stage 1: Discovery'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Convert log level string to constant
    
    log_level = getattr(logging, args.log_level)
    
    # Setup logging
    log_file = setup_logging("discovery", log_level=log_level)
    print(f"\n📝 Logging to: {log_file}\n")
    
    try:
        # Run Stage 1
        result = run_stage1_discovery(headless=args.headless)
        
        # Display summary
        print("\n" + "=" * 70)
        print("DISCOVERY SUMMARY")
        print("=" * 70)
        print(f"Companies discovered: {result.total_companies}")
        print(f"Processos discovered: {result.total_processos}")
        print(f"Errors encountered: {len(result.errors)}")
        
        if result.errors:
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")
        
        print("=" * 70)
        
        # Exit code based on results
        if result.errors:
            print("\n⚠️ Stage 1 completed with errors")
            sys.exit(1)
        elif result.total_processos == 0:
            print("\n❌ Stage 1 failed: No processos discovered")
            sys.exit(1)
        else:
            print("\n✅ Stage 1 completed successfully")
            sys.exit(0)
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()