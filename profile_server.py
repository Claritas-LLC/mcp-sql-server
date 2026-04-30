import cProfile
import pstats
from pstats import SortKey

if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()

    import server  # This will run the server startup code

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(30)  # Show top 30 functions
    stats.dump_stats("profile_output.prof")
    print("Profile data saved to profile_output.prof")
