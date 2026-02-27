import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../models/user.dart';
import 'api_service.dart';
import '../../config/api_config.dart';

class AuthService extends ChangeNotifier {
  User? _currentUser;
  bool _isLoading = false;

  User? get currentUser => _currentUser;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _currentUser != null;

  // serverClientId must be your WEB OAuth Client ID (not Android)
  // This is needed to get an ID token for backend verification
  final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: ['email', 'profile'],
    serverClientId: '632068874977-pu6us2b6nmskod5l3nvdaffilo6s06ln.apps.googleusercontent.com',
  );

  // Initialize: check for existing token
  Future<void> init() async {
    final hasToken = await ApiService.hasToken();
    if (hasToken) {
      await fetchCurrentUser();
    }
  }

  // Sign in with Google
  Future<bool> signInWithGoogle() async {
    try {
      _isLoading = true;
      notifyListeners();

      final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
      if (googleUser == null) {
        _isLoading = false;
        notifyListeners();
        return false; // User cancelled
      }

      final GoogleSignInAuthentication googleAuth =
          await googleUser.authentication;
      final String? idToken = googleAuth.idToken;

      if (idToken == null) {
        throw Exception('Failed to get Google ID token');
      }

      // Send ID token to backend for JWT
      final response = await ApiService.post(
        ApiConfig.authGoogle,
        body: {'id_token': idToken},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        await ApiService.setToken(data['access_token']);
        await fetchCurrentUser();
        return true;
      } else {
        throw Exception('Authentication failed');
      }
    } catch (e) {
      debugPrint('Google sign-in error: $e');
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  // Fetch current user info
  Future<void> fetchCurrentUser() async {
    try {
      final response = await ApiService.get(ApiConfig.authMe);
      if (response.statusCode == 200) {
        _currentUser = User.fromJson(jsonDecode(response.body));
      } else {
        await logout();
      }
    } catch (e) {
      debugPrint('Fetch user error: $e');
      // Don't logout on network errors
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // Logout
  Future<void> logout() async {
    try {
      await ApiService.post(ApiConfig.authLogout);
    } catch (_) {}
    await ApiService.removeToken();
    await _googleSignIn.signOut();
    _currentUser = null;
    notifyListeners();
  }
}
