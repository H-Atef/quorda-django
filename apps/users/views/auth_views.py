from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from apps.users.serializers import RegisterSerializer, LoginSerializer, UserSerializer
from apps.users.services.auth_service import AuthService



@extend_schema(tags=['auth'])
class RegisterView(APIView):
     
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Register a new user",
        description="Create a new user account. Admin role is not allowed via this endpoint.",
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(response=UserSerializer, description="User registered successfully"),
            400: OpenApiResponse(description="Validation error", response=None),
        }
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AuthService.register_user(serializer.validated_data)
        return Response({
            'message': result['message'],
            'user': {
                'id': str(result['user'].id),
                'username': result['user'].username,
                'email': result['user'].email,
                'role': result['user'].role,
            }
        }, status=status.HTTP_201_CREATED)


@extend_schema(tags=['auth'])
class LoginView(APIView):
     
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login user",
        description="Authenticate using username or email, returns access and refresh tokens.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful", response=None),
            401: OpenApiResponse(description="Invalid credentials", response=None),
        }
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AuthService.authenticate_user(
            username_or_email=serializer.validated_data['username_or_email'],
            password=serializer.validated_data['password']
        )
        response = Response({
            'message': 'Login successful',
            'user': {
                'id': str(result['user'].id),
                'username': result['user'].username,
                'email': result['user'].email,
                'role': result['user'].role,
            },
            'access': result['access'],
            'refresh': result['refresh'],
        })
        response.set_cookie(
            key='refresh_token',
            value=result['refresh'],
            httponly=True,
            secure=False,
            samesite='Lax',
        )
        return response


@extend_schema(tags=['auth'])
class LogoutView(APIView):
     
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout user",
        description="Blacklist the refresh token to invalidate the session.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'refresh_token': {'type': 'string', 'description': 'Optional if token is sent in cookie'}
                }
            }
        },
        responses={
            200: OpenApiResponse(description="Successfully logged out", response=None),
            401: OpenApiResponse(description="Authentication failed or token invalid", response=None),
        }
    )
    def post(self, request):
        refresh_token = request.data.get('refresh_token') or request.COOKIES.get('refresh_token')
        if not refresh_token:
            raise AuthenticationFailed('Refresh token is required.')
        result = AuthService.logout_user(refresh_token)
        response = Response(result, status=status.HTTP_200_OK)
        response.delete_cookie('refresh_token')
        return response


@extend_schema(tags=['auth'])
class RefreshView(APIView):

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Refresh access token",
        description="Obtain a new access token using a refresh token from the request body or cookie.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'refresh': {'type': 'string', 'description': 'Optional if refresh token is sent in cookie'}
                }
            }
        },
        responses={
            200: OpenApiResponse(description="Token refreshed successfully", response=None),
            401: OpenApiResponse(description="Invalid or expired refresh token", response=None),
        }
    )
    def post(self, request):
        refresh_token = request.data.get('refresh') or request.data.get('refresh_token') or request.COOKIES.get('refresh_token')
        if not refresh_token:
            raise AuthenticationFailed('Refresh token is required.')
        serializer = TokenRefreshSerializer(data={'refresh': refresh_token})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        response = Response(data, status=status.HTTP_200_OK)
        if data.get('refresh'):
            response.set_cookie(
                key='refresh_token',
                value=data['refresh'],
                httponly=True,
                secure=False,
                samesite='Lax',
            )
        return response