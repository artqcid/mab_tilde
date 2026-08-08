/// @file
///	@ingroup 	minapi
///	@copyright	Copyright 2018 The Min-API Authors. All rights reserved.
///	@license	Use of this source code is governed by the MIT License found in the License.md file.

#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <deque>
#include <fstream>
#include <iostream>
#include <iterator>
#include <list>
#include <mutex>
#include <queue>
#include <string>
#include <sstream>
#include <thread>
#include <vector>
#include <functional>
#include <unordered_map>
#include <utility>

#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-variable"
#endif

// Windows Header Guard - suppress conflicts with WinUser.h
// Undefine any previously defined macros first
#ifdef NOMINMAX
#undef NOMINMAX
#endif
#ifdef WIN32_LEAN_AND_MEAN
#undef WIN32_LEAN_AND_MEAN
#endif
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

#include "readerwriterqueue/readerwriterqueue.h"

#ifdef __clang__
#pragma clang diagnostic pop
#endif

#include "murmur/Murmur3.h" // used for constexpr hash function

// ONLY MSP - skip max, jitter, ui headers that cause conflicts
#include "c74_msp.h"

using c74::max::t_atom_long;
using c74::max::t_ptr_int;

namespace c74::min {

// ============================================================================
// Basic Types
// ============================================================================

using uchar = unsigned char;

using std::string;
using std::vector;

template <class T>
using unique_ptr = std::unique_ptr<T>;

using number = double;
using sample = double;
struct anything
{};

using numbers = std::vector<number>;
using ints = std::vector<int>;
using strings = std::vector<std::string>;

template <size_t count>
using samples = std::array<sample, count>;

using sample_vector = std::vector<sample>;

// The title and description types are just strings.
// However, we have to define them unambiguously for the argument parsing in the attribute.
class title : public std::string
{
    using std::string::string; // inherit constructors
};

class description : public std::string
{
    using std::string::string; // inherit constructors
};

using symbol = string;

// ============================================================================
// Atoms - C++20 compile-time string wrapper
// ============================================================================

class atoms
{
public:
    atoms() = default;
    
    template <typename... Ts>
    atoms(Ts&&... args) : m_atoms{ std::forward<Ts>(args)... } {}
    
    using const_iterator = std::vector<atom>::const_iterator;
    
    const_iterator begin() const { return m_atoms.begin(); }
    const_iterator end() const { return m_atoms.end(); }
    const_iterator cbegin() const { return begin(); }
    const_iterator cend() const { return end(); }
    size_t size() const { return m_atoms.size(); }
    bool empty() const { return m_atoms.empty(); }
    const atom& operator[](size_t i) const { return m_atoms[i]; }
    atom& operator[](size_t i) { return m_atoms[i]; }
    
private:
    std::vector<atom> m_atoms;
};

// ============================================================================
// Object Base Class
// ============================================================================

template <typename T>
class object : public T
{
public:
    using super = T;
    
    object() : T() {}
    explicit object(const atoms& args) : T(args) {}
    virtual ~object() = default;
};

// ============================================================================
// Attribute System - C++20 compatible
// ============================================================================

template <typename T, typename... Args>
class attribute_base
{
public:
    using value_type = T;
    
protected:
    value_type m_value{};
    symbol m_name;
    title m_title;
    description m_description;
    T* m_owner = nullptr;
};

template <typename T>
class attribute : public attribute_base<T>
{
public:
    using base = attribute_base<T>;
    
    template <typename U>
    explicit attribute(U* owner, const symbol& name, const T& default_value, const description& desc = "")
        : base(name, default_value, desc)
    {
        if (owner) {
            this->m_owner = owner;
            owner->register_attribute(name, this);
        }
    }
    
    operator const T&() const { return this->m_value; }
    const T& operator()() const { return this->m_value; }
    
    void operator=(const T& value) { this->m_value = value; }
    
private:
    template <typename U>
    attribute(U* owner, const symbol& name, const T& default_value, const description& desc, int)
        : base(name, default_value, desc)
    {
        if (owner) {
            this->m_owner = owner;
            owner->register_attribute(name, this);
        }
    }
};

// ============================================================================
// Message System
// ============================================================================

template <typename T>
class message
{
public:
    using handler_type = std::function<void(const atoms&)>;
    
    message(T* owner, const symbol& name, const description& desc = "")
        : m_owner(owner), m_name(name), m_description(desc)
    {
        if (owner) {
            owner->register_message(name, this);
        }
    }
    
    void operator()(const atoms& args = {})
    {
        if (m_handler) {
            m_handler(args);
        }
    }
    
    template <typename F>
    void set_handler(F&& f) { m_handler = std::forward<F>(f); }
    
private:
    T* m_owner;
    symbol m_name;
    description m_description;
    handler_type m_handler;
};

// ============================================================================
// Attribute Macros
// ============================================================================

#define MIN_ATTRIBUTE_FUNCTION { return {}; }

// ============================================================================
// Argument System
// ============================================================================

template <typename T>
class argument
{
public:
    using handler_type = std::function<void(const T&)>;
    
    argument(T* owner, const symbol& name, const description& desc, handler_type handler = nullptr)
        : m_owner(owner), m_name(name), m_description(desc), m_handler(std::move(handler))
    {
        if (owner) {
            owner->register_argument(name, this);
        }
    }
    
private:
    T* m_owner;
    symbol m_name;
    description m_description;
    handler_type m_handler;
};

// ============================================================================
// Min Class Attributes Macro
// ============================================================================

#define min_class_attributes(tags) static constexpr const char* class_tags = tags

using symbol;

template <typename T>
class inlet
{
public:
    inlet(T* owner, const char* description = "") {}
};

template <typename T>
class outlet
{
public:
    outlet(T* owner, const char* description = "") {}
};

template <typename T>
class message
{
public:
    message(T* owner, const char* name, const char* desc = "") {}
};

// ============================================================================
// DSP Operators
// ============================================================================

class audio_bundle
{
public:
    audio_bundle() : m_channels(1), m_frames(64) {}
    int channel_count() const { return m_channels; }
    int frame_count() const { return m_frames; }
    float* samples(int ch) { return m_data + ch * m_frames; }
    const float* samples(int ch) const { return m_data + ch * m_frames; }
    
private:
    int m_channels;
    int m_frames;
    float m_data[16 * 1024]; // max 16 channels, 1024 frames each
};

template <typename T>
class audio_operator
{
public:
    virtual void operator()(audio_bundle input, audio_bundle output) = 0;
};

template <typename T>
class dsp_spray : public audio_operator<T>
{
public:
    dsp_spray(T* owner, const char* name = "") {}
};

// ============================================================================
// Output Functions
// ============================================================================

namespace detail {
    template <typename... Args>
    void cout_func(Args&&... args);
}

using detail::cout_func;

#define MIN_EXTERNAL(T) \
    extern "C" { \
        __declspec(dllexport) int main() { \
            return 0; \
        } \
    }

namespace cout {
    inline void operator<<(const char* s) {}
    inline void operator<<(const std::string& s) {}
    inline void operator<<(int n) {}
    inline void operator<<(double d) {}
    inline void endl(std::ostream&) {}
}