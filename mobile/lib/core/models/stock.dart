class ComparisonItem {
  final String symbol;
  final String instrumentName;
  final double oldPrice;
  final double newPrice;
  final double pctChange;
  final double volumeRatio;
  final double volume;

  ComparisonItem({
    required this.symbol,
    required this.instrumentName,
    required this.oldPrice,
    required this.newPrice,
    required this.pctChange,
    required this.volumeRatio,
    required this.volume,
  });

  factory ComparisonItem.fromJson(Map<String, dynamic> json) {
    return ComparisonItem(
      symbol: json['Symbol'] ?? '',
      instrumentName: json['InstrumentName'] ?? '',
      oldPrice: (json['OldPrice'] ?? 0).toDouble(),
      newPrice: (json['NewPrice'] ?? 0).toDouble(),
      pctChange: (json['PctChange'] ?? 0).toDouble(),
      volumeRatio: (json['VolumeRatio'] ?? 0).toDouble(),
      volume: (json['Volume'] ?? 0).toDouble(),
    );
  }
}

class StockComparison {
  final String date1;
  final String date2;
  final int count;
  final List<ComparisonItem> gainers;
  final List<ComparisonItem> losers;
  final List<ComparisonItem> data;

  StockComparison({
    required this.date1,
    required this.date2,
    required this.count,
    required this.gainers,
    required this.losers,
    required this.data,
  });

  factory StockComparison.fromJson(Map<String, dynamic> json) {
    return StockComparison(
      date1: json['date1'] ?? '',
      date2: json['date2'] ?? '',
      count: json['count'] ?? 0,
      gainers: (json['gainers'] as List? ?? [])
          .map((e) => ComparisonItem.fromJson(e))
          .toList(),
      losers: (json['losers'] as List? ?? [])
          .map((e) => ComparisonItem.fromJson(e))
          .toList(),
      data: (json['data'] as List? ?? [])
          .map((e) => ComparisonItem.fromJson(e))
          .toList(),
    );
  }
}

class SymbolSearchResult {
  final String symbol;
  final String name;

  SymbolSearchResult({required this.symbol, required this.name});

  factory SymbolSearchResult.fromJson(Map<String, dynamic> json) {
    return SymbolSearchResult(
      symbol: json['symbol'] ?? '',
      name: json['name'] ?? '',
    );
  }
}
