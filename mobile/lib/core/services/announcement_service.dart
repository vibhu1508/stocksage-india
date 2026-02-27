import '../models/announcement.dart';
import 'api_service.dart';
import '../../config/api_config.dart';

class AnnouncementService {
  // Get NSE announcements for a symbol
  static Future<List<NSEAnnouncement>> getNSEAnnouncements(
    String symbol, {
    String? fromDate,
    String? toDate,
    int limit = 100,
  }) async {
    final params = <String, String>{'limit': limit.toString()};
    if (fromDate != null) params['from_date'] = fromDate;
    if (toDate != null) params['to_date'] = toDate;

    final response = await ApiService.get(
      ApiConfig.nseAnnouncements(symbol),
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    return (data['announcements'] as List? ?? [])
        .map((e) => NSEAnnouncement.fromJson(e))
        .toList();
  }

  // Get BSE announcements
  static Future<Map<String, dynamic>> getBSEAnnouncements({
    String? scripCode,
    String? fromDate,
    String? toDate,
    int page = 1,
  }) async {
    final params = <String, String>{'page': page.toString()};
    if (scripCode != null) params['scrip_code'] = scripCode;
    if (fromDate != null) params['from_date'] = fromDate;
    if (toDate != null) params['to_date'] = toDate;

    final response = await ApiService.get(
      ApiConfig.bseAnnouncements,
      queryParams: params,
    );
    final data = ApiService.decodeResponse(response);
    final announcements = (data['announcements'] as List? ?? [])
        .map((e) => BSEAnnouncement.fromJson(e))
        .toList();
    return {
      'announcements': announcements,
      'total_pages': data['total_pages'] ?? 0,
      'current_page': data['current_page'] ?? 1,
    };
  }
}
