import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiService {
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'access_token';

  // Get stored JWT token
  static Future<String?> getToken() async {
    return await _storage.read(key: _tokenKey);
  }

  // Store JWT token
  static Future<void> setToken(String token) async {
    await _storage.write(key: _tokenKey, value: token);
  }

  // Remove token (logout)
  static Future<void> removeToken() async {
    await _storage.delete(key: _tokenKey);
  }

  // Check if user has a stored token
  static Future<bool> hasToken() async {
    final token = await getToken();
    return token != null && token.isNotEmpty;
  }

  // GET request with auth header
  static Future<http.Response> get(
    String url, {
    Map<String, String>? queryParams,
  }) async {
    final token = await getToken();
    final uri = Uri.parse(url).replace(queryParameters: queryParams);

    return await http
        .get(
          uri,
          headers: {
            'Content-Type': 'application/json',
            if (token != null) 'Authorization': 'Bearer $token',
          },
        )
        .timeout(const Duration(seconds: 30));
  }

  // POST request with auth header
  static Future<http.Response> post(
    String url, {
    Map<String, dynamic>? body,
  }) async {
    final token = await getToken();

    return await http
        .post(
          Uri.parse(url),
          headers: {
            'Content-Type': 'application/json',
            if (token != null) 'Authorization': 'Bearer $token',
          },
          body: body != null ? jsonEncode(body) : null,
        )
        .timeout(const Duration(seconds: 30));
  }

  // DELETE request with auth header
  static Future<http.Response> delete(String url) async {
    final token = await getToken();

    return await http
        .delete(
          Uri.parse(url),
          headers: {
            'Content-Type': 'application/json',
            if (token != null) 'Authorization': 'Bearer $token',
          },
        )
        .timeout(const Duration(seconds: 30));
  }

  // Helper to decode JSON response
  static Map<String, dynamic> decodeResponse(http.Response response) {
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else if (response.statusCode == 401) {
      throw Exception('Unauthorized — please login again');
    } else {
      try {
        final error = jsonDecode(response.body);
        throw Exception(
          error['detail'] ?? 'Request failed (${response.statusCode})',
        );
      } catch (e) {
        if (e is Exception && e.toString().contains('detail')) rethrow;
        throw Exception(
          'Server error (${response.statusCode}): ${response.body.length > 100 ? response.body.substring(0, 100) : response.body}',
        );
      }
    }
  }
}
