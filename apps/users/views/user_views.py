from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.users.serializers import UserSerializer, UserUpdateSerializer
from apps.users.permissions import IsAdmin
from apps.users.services.user_service import UserService
from apps.users.helpers.constants import UserRole
from apps.common.pagination import paginate, parse_page, parse_page_size


PAGE_PARAM = OpenApiParameter(
    name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=1, description='Page number.',
)
PAGE_SIZE_PARAM = OpenApiParameter(
    name='page_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    required=False, default=20, description='Number of items per page.',
)


class UserListView(APIView):
    
    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        summary="List all users",
        description="Admin only",
        tags=['users'],
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM],
        responses={
            200: OpenApiResponse(response=UserSerializer(many=True), description="List of users"),
            403: OpenApiResponse(description="Forbidden", response=None),
        }
    )
    def get(self, request):
        page = parse_page(request)
        page_size = parse_page_size(request)
        users = UserService.list_users()
        items, meta = paginate(users, page, page_size)
        serializer = UserSerializer(items, many=True)
        return Response({'results': serializer.data, **meta}, status=status.HTTP_200_OK)


class UserDetailView(APIView):
    
    permission_classes = [IsAuthenticated]

    def _get_target_user(self, request):
        user_id = request.query_params.get('user_id')
        if request.user.role == UserRole.ADMIN and user_id:
            return UserService.get_user_by_id(user_id)
        return request.user

    @extend_schema(
        summary="Get user details",
        description="Returns current user. Admin can pass ?user_id to get another user.",
        parameters=[OpenApiParameter('user_id', str, required=False)],
        tags=['users'],
        responses={
            200: OpenApiResponse(response=UserSerializer, description="User data"),
            404: OpenApiResponse(description="User not found", response=None),
        }
    )
    def get(self, request):
        target = self._get_target_user(request)
        serializer = UserSerializer(target)
        return Response(serializer.data)

    @extend_schema(
        summary="Full update user",
        parameters=[OpenApiParameter('user_id', str, required=False)],
        request=UserUpdateSerializer,
        tags=['users'],
        responses={
            200: OpenApiResponse(response=UserUpdateSerializer, description="Updated user data"),
            400: OpenApiResponse(description="Validation error", response=None),
            404: OpenApiResponse(description="User not found", response=None),
        }
    )
    def put(self, request):
        target = self._get_target_user(request)
        serializer = UserUpdateSerializer(target, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = UserService.update_user(
            target,
            serializer.validated_data,
            partial=False,
            requesting_user=request.user,
        )
        return Response(UserUpdateSerializer(updated).data)

    @extend_schema(
        summary="Partial update user",
        parameters=[OpenApiParameter('user_id', str, required=False)],
        request=UserUpdateSerializer,
        tags=['users'],
        responses={
            200: OpenApiResponse(response=UserUpdateSerializer, description="Updated user data"),
            400: OpenApiResponse(description="Validation error", response=None),
            404: OpenApiResponse(description="User not found", response=None),
        }
    )
    def patch(self, request):
        target = self._get_target_user(request)
        serializer = UserUpdateSerializer(target, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = UserService.update_user(
            target,
            serializer.validated_data,
            partial=True,
            requesting_user=request.user,
        )
        return Response(UserUpdateSerializer(updated).data)

    @extend_schema(
        summary="Delete user",
        parameters=[OpenApiParameter('user_id', str, required=False)],
        tags=['users'],
        responses={
            204: OpenApiResponse(description="User deleted successfully", response=None),
            404: OpenApiResponse(description="User not found", response=None),
        }
    )
    def delete(self, request):
        target = self._get_target_user(request)
        UserService.delete_user(target)
        return Response(status=status.HTTP_204_NO_CONTENT)
