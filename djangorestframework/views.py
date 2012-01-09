"""
The :mod:`views` module provides the Views you will most probably
be subclassing in your implementation.

By setting or modifying class attributes on your view, you change it's predefined behaviour.
"""

from django.core.urlresolvers import set_script_prefix, get_script_prefix
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from djangorestframework.compat import View as DjangoView
from djangorestframework.response import Response, ErrorResponse
from djangorestframework.mixins import *
from djangorestframework import resources, renderers, parsers, authentication, permissions, status
from djangorestframework.utils.description import get_name, get_description


__all__ = (
    'View',
    'ModelView',
    'InstanceModelView',
    'ListModelView',
    'ListOrCreateModelView'
)



class View(ResourceMixin, RequestMixin, ResponseMixin, AuthMixin, DjangoView):
    """
    Handles incoming requests and maps them to REST operations.
    Performs request deserialization, response serialization, authentication and input validation.
    """

    """
    The resource to use when validating requests and filtering responses,
    or `None` to use default behaviour.
    """
    resource = None

    """
    List of renderers the resource can serialize the response with, ordered by preference.
    """
    renderers = renderers.DEFAULT_RENDERERS

    """
    List of parsers the resource can parse the request with.
    """
    parsers = parsers.DEFAULT_PARSERS

    """
    List of all authenticating methods to attempt.
    """
    authentication = ( authentication.UserLoggedInAuthentication,
                       authentication.BasicAuthentication )

    """
    List of all permissions that must be checked.
    """
    permissions = ( permissions.FullAnonAccess, )


    @classmethod
    def as_view(cls, **initkwargs):
        """
        Override the default :meth:`as_view` to store an instance of the view
        as an attribute on the callable function.  This allows us to discover
        information about the view when we do URL reverse lookups.
        """
        view = super(View, cls).as_view(**initkwargs)
        view.cls_instance = cls(**initkwargs)
        return view


    @property
    def allowed_methods(self):
        """
        Return the list of allowed HTTP methods, uppercased.
        """
        return [method.upper() for method in self.http_method_names if hasattr(self, method)]


    def http_method_not_allowed(self, request, *args, **kwargs):
        """
        Return an HTTP 405 error if an operation is called which does not have a handler method.
        """
        raise ErrorResponse(status.HTTP_405_METHOD_NOT_ALLOWED,
                            {'detail': 'Method \'%s\' not allowed on this resource.' % self.method})


    def initial(self, request, *args, **kargs):
        """
        Hook for any code that needs to run prior to anything else.
        Required if you want to do things like set `request.upload_handlers` before
        the authentication and dispatch handling is run.
        """
        pass


    def add_header(self, field, value):
        """
        Add *field* and *value* to the :attr:`headers` attribute of the :class:`View` class.
        """
        self.headers[field] = value


    # Note: session based authentication is explicitly CSRF validated,
    # all other authentication is CSRF exempt.
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.args = args
        self.kwargs = kwargs
        self.headers = {}

        # Calls to 'reverse' will not be fully qualified unless we set the scheme/host/port here.
        orig_prefix = get_script_prefix()
        if not (orig_prefix.startswith('http:') or orig_prefix.startswith('https:')):
            prefix = '%s://%s' % (request.is_secure() and 'https' or 'http', request.get_host())
            set_script_prefix(prefix + orig_prefix)

        try:
            self.initial(request, *args, **kwargs)

            # Authenticate and check request has the relevant permissions
            self._check_permissions()

            # Get the appropriate handler method
            if self.method.lower() in self.http_method_names:
                handler = getattr(self, self.method.lower(), self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed

            response_obj = handler(request, *args, **kwargs)

            # Allow return value to be either HttpResponse, Response, or an object, or None
            if isinstance(response_obj, HttpResponse):
                return response_obj
            elif isinstance(response_obj, Response):
                response = response_obj
            elif response_obj is not None:
                response = Response(status.HTTP_200_OK, response_obj)
            else:
                response = Response(status.HTTP_204_NO_CONTENT)

            if request.method == 'OPTIONS':
                # do not filter the response for HTTP OPTIONS, else the response fields are lost,
                # as they do not correspond with model fields
                response.cleaned_content = response.raw_content
            else:
                # Pre-serialize filtering (eg filter complex objects into natively serializable types)
                response.cleaned_content = self.filter_response(response.raw_content)

        except ErrorResponse, exc:
            response = exc.response

        set_script_prefix(orig_prefix)
        return self.final(request, response, *args, **kwargs)

    def options(self, request, *args, **kwargs):
        response_obj = {
            'name': get_name(self),
            'description': get_description(self),
            'renders': self._rendered_media_types,
            'parses': self._parsed_media_types,
        }
        form = self.get_bound_form()
        if form is not None:
            field_name_types = {}
            for name, field in form.fields.iteritems():
                field_name_types[name] = field.__class__.__name__
            response_obj['fields'] = field_name_types
        return response_obj

    def final(self, request, response, *args, **kargs):
        """
        Hook for any code that needs to run after everything else in the view.
        """
        # Always add these headers.
        response.headers['Allow'] = ', '.join(self.allowed_methods)
        # sample to allow caching using Vary http header
        response.headers['Vary'] = 'Authenticate, Accept'

        # merge with headers possibly set at some point in the view
        response.headers.update(self.headers)
        return self.render(response)


class ModelView(View):
    """
    A RESTful view that maps to a model in the database.
    """
    resource = resources.ModelResource

class InstanceModelView(InstanceMixin, ReadModelMixin, UpdateModelMixin, DeleteModelMixin, ModelView):
    """
    A view which provides default operations for read/update/delete against a model instance.
    """
    _suffix = 'Instance'

class ListModelView(ListModelMixin, ModelView):
    """
    A view which provides default operations for list, against a model in the database.
    """
    _suffix = 'List'

class ListOrCreateModelView(ListModelMixin, CreateModelMixin, ModelView):
    """
    A view which provides default operations for list and create, against a model in the database.
    """
    _suffix = 'List'
