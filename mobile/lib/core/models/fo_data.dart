class NiftyData {
  final String date;
  final int futuresCount;
  final int optionsCount;
  final List<Map<String, dynamic>> futures;
  final List<Map<String, dynamic>> options;

  NiftyData({
    required this.date,
    required this.futuresCount,
    required this.optionsCount,
    required this.futures,
    required this.options,
  });

  factory NiftyData.fromJson(Map<String, dynamic> json) {
    return NiftyData(
      date: json['date'] ?? '',
      futuresCount: json['futures_count'] ?? 0,
      optionsCount: json['options_count'] ?? 0,
      futures: List<Map<String, dynamic>>.from(json['futures'] ?? []),
      options: List<Map<String, dynamic>>.from(json['options'] ?? []),
    );
  }
}

class FOData {
  final String date;
  final int count;
  final List<Map<String, dynamic>> data;

  FOData({required this.date, required this.count, required this.data});

  factory FOData.fromJson(Map<String, dynamic> json) {
    return FOData(
      date: json['date'] ?? json['symbol'] ?? '',
      count: json['count'] ?? 0,
      data: List<Map<String, dynamic>>.from(json['data'] ?? []),
    );
  }
}
