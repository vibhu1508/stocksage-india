class ApiConfig {
  // Render backend URL
  static const String baseUrl = 'https://stocksage-india.onrender.com';
  static const String apiUrl = '$baseUrl/api';

  // Auth endpoints
  static const String authGoogle = '$apiUrl/auth/google/mobile';
  static const String authMe = '$apiUrl/auth/me';
  static const String authLogout = '$apiUrl/auth/logout';
  static const String authOnboarding = '$apiUrl/auth/onboarding';
  static const String authOnboardingSkip = '$apiUrl/auth/onboarding/skip';

  // Stock endpoints
  static const String stockSymbols = '$apiUrl/stocks/symbols';
  static const String stockSearch = '$apiUrl/stocks/search';
  static const String stockCompare = '$apiUrl/stocks/compare';

  // F&O endpoints
  static const String foNifty = '$apiUrl/fo/nifty';
  static const String foFuturesAnalysis = '$apiUrl/fo/futures-analysis';
  static String foFutures(String symbol) => '$apiUrl/fo/futures/$symbol';
  static String foOptions(String symbol) => '$apiUrl/fo/options/$symbol';
  static const String foFuturesTable = '$apiUrl/fo/futures-table';

  // Announcement endpoints
  static String nseAnnouncements(String symbol) =>
      '$apiUrl/announcements/nse/$symbol';
  static const String bseAnnouncements = '$apiUrl/announcements/bse';
  static const String bseScripCodes = '$apiUrl/announcements/bse/scrip-codes';

  // Market data endpoints
  static const String marketLive = '$apiUrl/market/live';
  static const String marketSessionStatus = '$apiUrl/market/session-status';
  static const String dhanChartBootstrap = '$apiUrl/market/dhan/chart/bootstrap';
  static const String dhanChartHistory = '$apiUrl/market/dhan/chart/history';
  static const String dhanChartLatest = '$apiUrl/market/dhan/chart/latest';
  static const String dhanQuoteDepth = '$apiUrl/market/dhan/quote/depth';

  // Autocomplete
  static const String nseAutocomplete =
      '$apiUrl/announcements/nse/autocomplete';

  // Top stocks
  static const String topStocks = '$apiUrl/market/top-stocks';
  static const String topLosers = '$apiUrl/market/top-losers';

  // Strategy detail endpoints
  static String strategySymbolData(String symbol) => '$apiUrl/strategy/symbol-data/$symbol';
  static String strategyYearwiseData(String symbol) => '$apiUrl/strategy/yearwise-data/$symbol';

  // Learn
  static const String learnVideos = '$apiUrl/learn/videos';
  static const String learnSearch = '$apiUrl/learn/search';

  // StockSage AI assistant
  static const String chatTranscribe = '$apiUrl/chat/transcribe';
  // WebSocket for the streaming chat (ws/wss derived from baseUrl).
  static String chatWs(String? token) {
    final wsBase = baseUrl.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    final q = (token != null && token.isNotEmpty) ? '?token=${Uri.encodeComponent(token)}' : '';
    return '$wsBase/api/chat/ws$q';
  }

  // Portfolio endpoints
  static const String portfolioHoldings = '$apiUrl/portfolio/holdings';
  static const String portfolioHoldingsLive = '$apiUrl/portfolio/holdings/live';
  static String portfolioLotSize(String symbol) => '$apiUrl/portfolio/lot-size/$symbol';
  static String portfolioDerivativeContracts(String symbol) => '$apiUrl/portfolio/derivatives/contracts/$symbol';
}
