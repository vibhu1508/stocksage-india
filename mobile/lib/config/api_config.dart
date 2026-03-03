class ApiConfig {
  // Render backend URL
  static const String baseUrl = 'https://stocksage-india.onrender.com';
  static const String apiUrl = '$baseUrl/api';

  // Auth endpoints
  static const String authGoogle = '$apiUrl/auth/google/mobile';
  static const String authMe = '$apiUrl/auth/me';
  static const String authLogout = '$apiUrl/auth/logout';

  // Stock endpoints
  static const String stockSymbols = '$apiUrl/stocks/symbols';
  static const String stockSearch = '$apiUrl/stocks/search';
  static const String stockCompare = '$apiUrl/stocks/compare';

  // F&O endpoints
  static const String foNifty = '$apiUrl/fo/nifty';
  static String foFutures(String symbol) => '$apiUrl/fo/futures/$symbol';
  static String foOptions(String symbol) => '$apiUrl/fo/options/$symbol';

  // Announcement endpoints
  static String nseAnnouncements(String symbol) =>
      '$apiUrl/announcements/nse/$symbol';
  static const String bseAnnouncements = '$apiUrl/announcements/bse';
  static const String bseScripCodes = '$apiUrl/announcements/bse/scrip-codes';

  // Market data endpoints
  static const String marketLive = '$apiUrl/market/live';

  // Autocomplete
  static const String nseAutocomplete =
      '$apiUrl/announcements/nse/autocomplete';

  // Top stocks
  static const String topStocks = '$apiUrl/market/top-stocks';
  static const String topLosers = '$apiUrl/market/top-losers';

  // Learn
  static const String learnVideos = '$apiUrl/learn/videos';
  static const String learnSearch = '$apiUrl/learn/search';
}
