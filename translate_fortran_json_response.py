import requests

import csv
import time
import argparse
import os
import json
import re


# --- Configuration ---
API_URL = os.getenv("API_URL", "http://localhost:8000/v1/chat/completions")
MODEL = os.getenv("MODEL_ID", "")



SYSTEM_PROMPT = """
You are given Fortran 77 code that contain ESOPE extensions.
ESOPE is an extension of Fortran designed for structured memory management, based on the concept of segments (SEGMENT, SEGINI, SEGACT, SEGDES, SEGSUP, SEGADJ, etc>
The goal is to translate this legacy ESOPE-Fortran code into modern Fortran (Fortran 2008).
You must follow the requirements to translate the code.

Requirements:

1. Importing Code and Declarations
    1.1 Definition
        It refers to all mechanisms used to bring externally defined program elements—such as variables, constants, types, interfaces, and procedures—into the scope of a source file or program unit so they can be referenced without redefining them locally.
        In legacy Fortran, sharing functions across files was done using two mechanisms: the INCLUDE directive, which simply copy-pasted source code at compile time, and the EXTERNAL attribute, which informed the compiler that a procedure or a variable existed somewhere else.
        The EXTERNAL statement in Fortran77 specifies subroutines or functions as external, and allows their symbolic names to be used as actual arguments (e.g. EXTERNAL proc [, proc] ..).
        The source code uses two inclusion statements: the C style preprocessor directive #include (e.g #include <implicit.h>), and the standard FORTRAN 77 inclusion statement include (e.g include "constants.inc"). The argument can be delimited in <>, ‘’ or “”. The argument consists of a name and an extension. Examples of extensions are .h, .inc, .seg (esope-specific).
        •	Legacy mechanisms: INCLUDE, include, #include, EXTERNAL
        •	Modern mechanisms: use :: module_name
        In ESOPE-Fortran projects, the file PSTR.inc is a segment structural descriptor used to define and manage metadata for project segments. It contains information about identification, referencing, and indexing information for all segments associated with a project (e.g., book, user, tlib). Since PSTR is a segment descriptor rather than a functional unit, in modern Fortran, it’s been converted to str_m module ensuring modular dependencies are handled.
    1.2 Requirements
        1.2.1 All inclusion statements (INCLUDE, include, #include) must be commented out during translation in modern Fortran, as their functionalities are replaced by modular use :: dependencies.
        1.2.2 For each inclusion statement with argument name.ext, the original extension is dropped and _m is appended to form the corresponding Fortran module filename name_m.F90. The associated module is then expected to be name_m. Example:
        #include <constants.h> → comment the include and use use :: constants_m.
        1.2.3  PSTR.inc: The directive #include "PSTR.inc" must be commented as ! [ooo] empty #include PSTR.inc The corresponding module has already been converted to str_m, so the translation must explicitly import it using use :: str_m.
        1.2.4 #include "PSTR.inc" ****must be commented with ! [ooo] empty #include PSTR.inc and include the corresponding module for `pstr` using `use :: str_m`
	If a line is exactly '#include "PSTR.inc"' then replace it with: '! [ooo] empty #include PSTR.inc 
	use :: str_m'
        1.2.5 For each EXTERNAL procname declaration, search the codebase for a module or source file that defines a procedure named procname (regardless of the containing filename). If such a definition exists, replaces the EXTERNAL declaration with an appropriate use :: module_name that exposes procname. If no existing definition is found, the translator creates a new module file procname_m.f90 containing the procedure and its interface, and then imports it with use :: procname_m
        1.2.6 Exception: mypnt (ESOPE library function)
            1.2.6.1 Context: mypnt is an ESOPE library function used with segments. It returns an integer pointer referencing those segments. Although declared with EXTERNAL, it belongs to the ESOPE library and is not handled like regular external procedures. Legacy behaviour: All segments shared the same mypnt library function.
            Modern behaviour: Segments → modules. Each module now requires its own mypnt function.
            1.2.6.2 When encountering mypnt(...) calls, identify the segment context from the surrounding scope or variable being assigned to.
            
            Example: In ESOPE, the code:
            pointeur bk.book
            bk = mypnt(lib, iord)
            
            is translated into:
            type(book), pointer :: bk
            bk => book_mypnt(lib, iord)

2. Dimensioning variables
    2.1 Definition
        ESOPE introduce dimensioning variables and dimensioning expressions that allow array dimensions within segments to be determined at runtime. This feature applies only to arrays defined inside segments and enables flexible memory allocation (e.g., ubbcnt, or expressions such as ubbcnt*1.1 for buffer extension). Dimensioning variable is a scalar variable used to define the size of arrays declared inside a segment.
    2.2 Requirement
        When translating segments to modern Fortran, all dimensioning variables associated with a segment must be explicitly declared between the start and end markers of the commented include block( ! [ooo] #include segmentname.seg and ! [ooo] #end-include segmentname.seg ).
        Any variable required to specify array dimensions or allocation sizes within the segment must be declared inside the markers, even if it may be declared elsewhere in the broader codebase. Assume no external context is available.
3. Pointer
    3.1 Definition
        In ESOPE fortran, an instance of a segment is referenced by a variable called a pointer. Once the pointer is known, it can be used to access all the fields contained in that segment. Each segment is created within a routine through a pointer, which also allows segments to be passed as arguments to subprograms. In ESOPE, pointers are implemented as Fortran integers, and they are sometimes declared explicitly as integers. However, in Fortran 2008, a dedicated pointer type exists, which is different from the integer type.
    3.2 Requirements
        If there is any pointer declaration in the format pointeur variable.segment ( means that variable is a pointer referencing the segment named segment) it should be translated as type(segment), pointer :: variable (here, segment is no longer a segment definition but a derived type, and variable is a pointer to an object of that type.
4. Obsolete statements
    4.1 Definition
        ESOPE statements that were needed in ESOPE, and no longer needed in Fortran 2008.
    4.2 Requirements
        The following subroutines and commands should be commented.
        'call oooeta(..)'
        'call actstr(..)'
        'segact, var1'
        'segdes,var1' 
        'call desstr(var2,'MOD')' 
5. Intent
    5.1 Definition
        Intent is used to specify if a function/subroutine parameter should be read only, or write only, or both.
    5.2 Requirements
        If the parameter is first read before being assigned(being written), then it must be at least in. Conversely, if it is first assigned before being accessed, then it must be out; If it is first access and then assigned, it is inOut (because it was passed by reference in FORTRAN 77). Parameters passed along to other routines depend on the intent of these other routines to know whether they are an access or an assignment
6. Operator %
    6.1 Definition
        In ESOPE segment fields are accessed using dot notation. In modern fortran it’s been changed to % operator.
        6.2 Requirements
        p.scalar or p.a(𝑖1, ..., 𝑖𝑛) will be respectively translated to p%scalar and p%a(𝑖1, ..., 𝑖𝑛).
7. Constant declarations
    7.1 Definition
        In ESOPE, named constants are defined using a type declaration followed by a separate parameter statement, for example:
        integer m
        parameter(m=2147483647)
        This declares m as an integer and assigns it a constant value using a separate parameter statement.
    7.2 Requirement
        ESOPE patterns of the form:
        integer m
        parameter(m=2147483647)
        must be translated into a single modern Fortran constant declaration that includes both the type kind and literal suffix:
        integer(kind=8), parameter :: m = 2147483647_8
        The translated declaration must use integer(kind=8) to explicitly define the integer kind. Use a single declaration combining the type, parameter attribute, and the :: syntax. Include the _8 kind suffix on the literal to match the declared kind.
8. Esope / expression
    8.1 Definition
        The Esope slash expression, used to get the size of an array.
    8.2 Requirement
        seg.arr(/1) will translate to size(seg%arr, dim=1)

9. Module creation and Naming
    9.1 Definition
        Module creation consists in transforming standalone SUBROUTINEs or FUNCTIONs into structured MODULEs in modern Fortran, in order to improve code organization, safety, and reusability.
    9.2 Requirements
        Each standalone SUBROUTINE or FUNCTION (e.g., subroutine area) must be encapsulated within a corresponding MODULE (e.g., module area_m). The original procedure must be placed inside the CONTAINS section of the module. 
        Also, IMPLICIT NONE must be systematically declared in both the module and all enclosed procedures to enforce explicit typing and prevent implicit variable declarations.



Following are the other files in the project for the reference for dependency:

1. book.seg
    c segment book
          integer bsize
          
          segment, book
           character*40 btitle
           integer bpages
           real budc
           integer bepub(bsize)
           integer bhash
          end segment
2. tlib.seg
    c data structure for modeling a book library
    c segment de t�te
    c bref(brcnt) : ordinal position in PSTR of book segments 
    c uref(urcnt) : ordinal positions in PSTR of user segments
    c bstatu(brcnt) : borrowed status of books 
          integer brcnt
          integer urcnt
          
          segment, tlib
           integer bref(brcnt)
           logical bstatu(brcnt)
           integer uref(urcnt)
          end segment
3. user.seg
    c segment user
    c ubb(ubbcnt) : ordinal positions of books borrowed by the user 
          integer ubbcnt
          segment, user
           character*40 uname
           integer ubb(ubbcnt)
          end segment
4.  borbk.E
    subroutine borbk(lib, name, title, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "user.seg"
    
    c arguments
           pointeur lib.PSTR
           character *(*) name
           character *(*) title
           logical verbose
    
    c external functions
           external mypnt
           integer mypnt
    
           external fndbk
           integer fndbk
    
           external fndur
           integer fndur
    
    c local variables
           integer libeta
    
           pointeur lb.tlib
           pointeur ur.user
    
           integer ibk
           integer iur
    
           if (verbose) write(*,'(1x, a)') 'borbk: begin'
    
           if (verbose) then
             write(*,'(1x, a, a, a, a)')
         &   'borbk: user ', trim(name), ' is borrowing book ', trim(title)
           endif
    
    
    c see whether the user exists in the structure
           iur = fndur(lib, name, .false.)
           if (iur .eq. 0) then
             write(*,'(1x, a)') 'cannot find user ', name
             return
           endif
           if (verbose) write(*,'(1x, a, i8.8)') 'borbk: iur = ', iur
    
    c see whether the book exists in the structure
           ibk = fndbk(lib, title, .false.)
           if (ibk .eq. 0) then
             write(*,'(1x, a, a)') 'cannot find book ', title
             return
           endif
           if (verbose) write(*,'(1x, a, i8.8)') 'borbk: ibk = ', ibk
    
    c activate the structure
           call oooeta(lib, libeta)
           call actstr(lib)
    
           lb = mypnt(lib,1)
           segact, lb
           brcnt = lb.bref(/1)
           urcnt = lb.uref(/1)
    
    c update borrowed status of the book
           if (lb.bstatu(ibk)) then
             write(*,'(1x, a, a)')
         &    'cannot borrow an already borrowed book ',
         &    title
             return
           else
             lb.bstatu(ibk) = .true.
           endif
    
    c update the borrowed books by the user
           ur = mypnt(lib, lb.uref(iur))
           segact, ur
           ubbcnt = ur.ubb(/1)
           ubbcnt = ubbcnt + 1
           segadj, ur
           ur.ubb(ubbcnt) = ibk
           segdes, ur*MOD
    
           segdes,lb*MOD
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
           if (verbose) write(*,'(1x, a)') 'borbk: end'
    
           end
 
5. delbk.E
    subroutine delfbk(lib, title, verbose)

    c      Delete a free book with the given 'title'.
    c      If the book with 'title" does not exist, then just ignore the action.
    c      If the book does exist, but it not free, then also ignore the action.
    
           implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    
    c arguments
           pointeur lib.PSTR
           character*(*) title
           logical verbose
    
    c external functions
           external mypnt
           integer mypnt
    
           external fndbk
           integer fndbk
    
    c local variables
           integer libeta
           integer iord
           integer jord
           integer ibk
           
           pointeur bk.book
           pointeur lb.tlib
    
           if (verbose) write(*,'(1x,a)') 'delfbk: begin'
    
    c find the ordinal of the book with given 'title'
           ibk = fndbk(lib, title, verbose)
    
           if ( ibk .eq. 0 ) then
             if ( verbose ) then
               write(*,'(1x,a,a,a)') 'delfbk: no book with title <',
         &     trim(title),
         &     '> action is ignored'
               write(*,'(1x,a)') 'delfbk: end'
             endif
             return
           endif
    
    c activate the structure
           call oooeta(lib, libeta)
           call actstr(lib)
    
    c activate the head segment of the structure
           lb = mypnt(lib,1)
           segact, lb
    
    c delete the book only if it is free
           if ( lb.bstatu(ibk) ) then
    
             if ( verbose ) then
               write(*,'(1x,a,a,a)') 'delfbk: book with title <',
         &     trim(title),
         &     '> is not free ; action is ignored'
               write(*,'(1x,a)') 'delfbk: end'
             endif
             segdes, lb*NOMOD
    
           else
    c delete the book segment
             iord = lb.bref(ibk)
             bk = mypnt(lib,iord)
             call suppnt(lib, iord)
             segsup, bk
             bk = 0
    
    c update the head segment of the structure
             lb.bref(ibk) = 0
             lb.bstatu(ibk) = .false.
             segdes, lb*MOD
           endif
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
    
           if (verbose) write(*,'(1x,a)') 'delfbk: end'
    
           end

6. fndbk.E
    integer function fndbk(lib, title, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    
    c arguments
          pointeur lib.pstr
          character*(*) title
          logical verbose
    
    c external functions
          external mypnt
          integer mypnt
    
    
    c local variables
          integer libeta
    
          pointeur bk.book
          pointeur lb.tlib
    
          integer ibk
          integer ibk2
          character*200 title1
          character*200 title2
    
          if (verbose) write(*,'(1x,a)') 'fndbk: begin'
    
          call oooeta(lib, libeta)
          call actstr(lib)
    
          lb = mypnt(lib,1)
          segact, lb
          urcnt = lb.uref(/1)
          brcnt = lb.bref(/1)
    
          title1 = title
          ibk = 0
          do ibk2 = 1, brcnt
            if ( lb.bref(ibk2) .ne. 0) then
              bk = mypnt(lib, lb.bref(ibk2))
              segact, bk
              title2 = bk.btitle
              segdes, bk*NOMOD
              if (title2 .eq. title1) then
                ibk = ibk2
                goto 100
              endif
            endif
          end do
    
     100  continue
          segdes, lb*NOMOD
    
          fndbk = ibk
    
    c deactivate the structure if activated on entry
          if(libeta.ne.1) call desstr(lib,'MOD')
    
          if (verbose) write(*,'(1x,a)') 'fndbk: end'
    
          end

7. fndur.E
    integer function fndur(lib, name, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "user.seg"
    
    c arguments
          pointeur lib.pstr
          character*(*) name
          logical verbose
    
    c external functions
          external mypnt
          integer mypnt
    
    c local variables
          integer libeta
    
          integer iur
          integer iur2
          character*200 name1
          character*200 name2
    
          pointeur ur.user
          pointeur lb.tlib
    
          if (verbose) write(*,'(1x,a)') 'fndur: begin'
    
          call oooeta(lib, libeta)
          call actstr(lib)
    
          lb = mypnt(lib,1)
          segact, lb
          urcnt = lb.uref(/1)
          brcnt = lb.bref(/1)
    
          name1 = name
    
          iur = 0
          do iur2=1, urcnt
            ur = mypnt(lib, lb.uref(iur2))
            segact, ur
            ubbcnt = ur.ubb(/1)
            name2 = ur.uname
            segdes, ur*NOMOD
    
            if (name2 .eq. name1) then
              iur = iur2
              goto 100
            end if
          end do
    
     100  continue
          segdes, lb*NOMOD
    
          fndur = iur
    
    c deactivate the structure if activated on entry
          if(libeta.ne.1) call desstr(lib,'MOD')
    
          if (verbose) write(*,'(1x,a)') 'fndur: end'
    
          end
8. genact.E
    subroutine genact(lib, acnt)
    implicit none
    
    #include "PSTR.inc"
    
    c arguments
          pointeur lib.PSTR
          integer acnt
    
          character*40 name
          character*40 title
          logical verbose
    
          real borpro
          real logpro
          parameter(borpro=0.50)
          parameter(logpro=0.001)
    
          integer iac
          integer ierr
          integer kerr
    
          real x
    
          real myunif
          external myunif
          write(*,'(1x,a)') 'genact: begin'
          write(*,'(1x,a,i8,a)') 'genact: generate ', acnt, ' actions ...'
          do iac=1,acnt
    
    
    c       -- log just a small fraction of the actions
            x = myunif()
            if ( x .lt. logpro ) then
                verbose = .true.
            else
                verbose = .false.
            endif
            if ( verbose ) then
                write(*,'(1x,a,i8,a,i8,a)')
         &      'genact: logging action ', iac, ' / ', acnt, ' ...'
            endif
    c       -- seclect a type of action and doit it
            x = myunif()
            if ( x .lt. borpro ) then
    c           -- a user borrows a free book
                kerr = 0
                call takusr(lib, name, ierr)
                kerr = kerr + ierr
                call takfbk(lib, title, ierr)
                kerr = kerr + ierr
                if ( kerr .eq. 0 ) then
                    call borbk(lib, name, title, verbose)
                endif
            else
    c           -- a user releases a borrowed book
                kerr = 0
                call takbor(lib, name, title, ierr)
                kerr = kerr + ierr
                if ( kerr .eq. 0 ) then
                    call relbk(lib, name, title, verbose)
                endif
            endif
          enddo
          write(*,'(1x,a)') 'genact: end'
          end
    
9. genbk.E
    subroutine genbk(lib, bcnt)
    implicit none
    
    #include "PSTR.inc"
    
    c arguments
          pointeur lib.PSTR
          integer bcnt
    
          character*(26*2) chars
          parameter(chars=
         &'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    
          integer ttlmin
          integer ttlmax
          parameter(ttlmin=len('Book_') + 1)
          parameter(ttlmax=40)
    
          integer pagmin
          integer pagmax
          parameter(pagmin=10)
          parameter(pagmax=300)
    
          real udcmin
          real udcmax
          parameter(udcmin=10.1)
          parameter(udcmax=99.1)
    
          integer ibk
          integer itt
          integer ich
    
          character*40 title
          integer pages
          real udc
    
          integer ttl
    
          real x
    
          real  myunif
          external  myunif
    
          write(*,'(1x,a)') 'genbk: begin'
          write(*,'(1x,a,i8,a)') 'generate ', bcnt, ' books ...'
    
          do ibk=1,bcnt
            title = ''
            x = myunif()
            ttl = ttlmin + x*(ttlmax - ttlmin)
    
            do itt=1,ttl
               x = myunif()
               ich = x*len(chars) + 1
               title(itt:itt) = chars(ich:ich)
            enddo
            
            title = 'Book_' // title
            x = myunif()
            pages = pagmin + x*(pagmax - pagmin)
            x = myunif()
            udc = udcmin + x*(udcmax - udcmin)
            call newbk(lib,title, pages, udc, .false.)
          enddo
          write(*,'(1x,a)') 'genbk: end'
          end
10. genusr.E
          subroutine genusr(lib, ucnt)
          implicit none
    
        #include "PSTR.inc"
    
        c arguments
          pointeur lib.PSTR
          integer ucnt
    
          character*(26*2) chars
          parameter(chars=
         &'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    
          integer nmlmin
          integer nmlmax
          parameter(nmlmin=len('User_') + 1)
          parameter(nmlmax=40)
    
          integer iur
          integer inm
          integer ich
    
          character*40 name
          integer nml
          real x
          real  myunif
          external  myunif
    
          write(*,'(1x,a)') 'genusr: begin'
          write(*,'(1x,a,i8,a)') 'generate ', ucnt, ' users ...'
    
          do iur=1,ucnt
            name = ''
            x = myunif()
            nml = nmlmin + x*(nmlmax - nmlmin)
            do inm=1,nml
               x = myunif()
               ich = x*len(chars) + 1
               name(inm:inm) = chars(ich:ich)
            enddo
            name = 'User_' // name
            call newusr(lib, name, .false.)
          enddo
          write(*,'(1x,a)') 'genusr: end'
          end

11. myunif.E
    real function myunif()
    c     Simple and portable random generator
    c     Return a uniform random real 'x' such that '0 <= x < 1'
    c
    c     >> Just for functional unit tests
    c     >> Do not use such generator in real application
    
          implicit none
    
          integer m
          integer a
          integer c
    
    c     Reference: https://cplusplus.com/reference/random/minstd_rand
    c     Minimal Standard algorithm, as described by Stephen K. Park and Keith W. Miller.
          parameter(m=2147483647)
          parameter(a=48271)
          parameter(c=0)
    
          logical debug
          parameter(debug=.false.)
    
    c     >> Double-width integer is required for updating 'state',
    c     >> otherwise negative values of 'state' will occur.
          integer*8 state
          save state
          data state /1/
    
          if ( debug ) then
            write(*,'(1x,a)') 'myunif: begin'
            write(*,'(1x,a,spi19)') 'myunif: state (before) = ', state
          endif
          state = mod(a*state + c, m)
          if ( state .lt. 0 ) then
            write(*,'(1x,a,spi19)')
         &    'myunif: stop on negative state = ', state
            stop
          endif
    
          myunif = real(state)/real(m)
    
          if ( debug ) then
            write(*,'(1x,a,spi19)') 'myunif: state (after) = ', state
            write(*,'(1x,a)') 'myunif: end'
          endif
          end

12. newbk.E
    subroutine newbk(lib, title, pages, udc, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    
    c arguments
           pointeur lib.PSTR
           character*(*) title
           integer pages
           real udc
           logical verbose
    
    c external functions
           external mypnt
           integer mypnt
    
           real myunif
           external myunif
    
           external fndbk
           integer fndbk
    
    c local variables
           integer libeta
    
           pointeur bk.book
           pointeur lb.tlib
    
           integer bszmin
           integer bszmax
           parameter(bszmin=100)
           parameter(bszmax=8000)
    
           integer dtmin
           integer dtmax
           parameter(dtmin=0)
           parameter(dtmax=2**15)
    
           integer hshmod
           parameter(hshmod=216091)
    
           integer idt
           integer jord
           real x
    
           if (verbose) write(*,'(1x,a)') 'newbk: begin'
    
           if ( fndbk(lib, title, verbose) .ne. 0 ) then
             if (verbose) then
               write(*,'(1x,a,a,a)') 'newbk: book with title <',
         &     trim(title),
         &     '> already exists ; action is ignored'
               write(*,'(1x,a)') 'newbk: end'
             endif
             return
           endif
    
    
    c activate the structure
           call oooeta(lib, libeta)
           call actstr(lib)
    
    c create a new book
           x = myunif()
           bsize = bszmin + x*(bszmax - bszmin)
    
           segini, bk
           bk.btitle = title
           bk.bpages = pages
           bk.budc   = udc
    
    c      -- generate random data to simutate the 'epub' format
           do idt=1, bsize
             x = myunif()
             bk.bepub(idt) = dtmin + x*(dtmax - dtmin)
           enddo
    
    c      -- compute the 'hash' of the 'epub' data
           bk.bhash = 0
           do idt=1, bsize
             bk.bhash = mod(bk.bhash + bk.bepub(idt), hshmod)
           enddo
    
           segdes, bk*MOD
    
    c add the new book to the structure
           call ajpnt(lib, bk, 'book ', 0, jord)
    
    c update the head segment of the structure
           lb = mypnt(lib,1)
           segact, lb
           urcnt = lb.uref(/1)
           brcnt = lb.bref(/1)
           brcnt = brcnt + 1
           segadj, lb
           lb.bref(brcnt) = jord
           lb.bstatu(brcnt) = .false.
           segdes, lb*MOD
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
    
           if (verbose) write(*,'(1x,a)') 'newbk: end'
    
           end

13. newlib.E
    subroutine newlib(lib)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    
    c arguments
           pointeur lib.pstr
    
    c local variables
           pointeur lb.tlib
           integer iord
           integer jord
    
           write(*,'(1x,a)') 'newlib: begin'
    
           call inistr(lib, 'library', 3, 0)
           call actstr(lib)
    
    
    c create the head segment
           brcnt  = 0
           urcnt  = 0
           segini, lb
           segdes, lb*MOD
    
    c add the head segment to the structure at head ordinal position (iord = 1)
           iord = 1
           call ajpnt(lib, lb, 'tlib', iord, jord)
    
           call desstr(lib,'MOD')
    
           write(*,'(1x,a)') 'newlib: end'
    
           end

14. newusr.E
    subroutine newusr(lib, name, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "user.seg"
    
    c arguments
           pointeur lib.PSTR
           character *(*) name
           logical verbose
    
    c external functions
           external mypnt
           integer mypnt
    
           external fndur
           integer fndur
    
    c local variables
           integer libeta
           integer  jord
           pointeur lb.tlib
           pointeur ur.user
    
           if (verbose) write(*,'(1x,a)') 'newusr: begin'
    
           if ( fndur(lib, name, verbose) .ne. 0 ) then
             if (verbose) then
               write(*,'(1x,a,a,a)') 'newusr: user with name <',
         &     trim(name),
         &     '> already exists ; action is ignored'
               write(*,'(1x,a)') 'newusr: end'
             endif
             return
           endif
    
    c activate the structure
           call oooeta(lib, libeta)
           call actstr(lib)
    
    c create a new book
           ubbcnt = 0
           segini, ur
           ur.uname = name
           segdes, ur*MOD
    
    c add the new book to the structure
           call ajpnt(lib, ur,'user', 0, jord)
    
    c update the head segment of the structure
           lb = mypnt(lib,1)
           segact, lb
           brcnt = lb.bref(/1)
           urcnt = lb.uref(/1)
           urcnt = urcnt + 1
           segadj, lb
           lb.uref(urcnt) = jord
           segdes, lb*MOD
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
    
           if (verbose) write(*,'(1x,a)') 'newusr: end'
           end


15. printlib.E
    subroutine prtlib(lib)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    #include "user.seg"
    
    c arguments
          pointeur lib.pstr
    
    c external functions
          external mypnt
          integer mypnt
    
    c local variables
          pointeur lb.tlib
          pointeur bk.book
          pointeur ur.user
          integer libeta
    
    c ibk index of a book
    c iur index of a user
    c ibor index of borrowed book
          integer ibk, iur, ibor
    
          write(*,'(1x,a)') 'prtlib: begin'
    
          call oooeta(lib, libeta)
          call actstr(lib)
    
          lb = mypnt(lib,1)
          segact, lb
    
          brcnt = lb.bref(/1)
          urcnt = lb.uref(/1)
    
          write(*,'(1x)')
          write(*,'(1x,a)') '-- books --'
          do ibk=1, brcnt
            if (lb.bref(ibk) .ne. 0) then
              bk = mypnt(lib, lb.bref(ibk))
              segact, bk
              write(*,'(1x,a)')
              write(*,'(1x,a,i8.8)')'book: index = ', ibk
              write(*,'(1x,a,a)')   '..... title = ', bk.btitle
              write(*,'(1x,a,i4)')  '..... pages = ', bk.bpages
              write(*,'(1x,a,f7.2)')'.....   udc = ', bk.budc
              write(*,'(1x,a,i8.8)') '.... bsize = ', bk.bepub(/1)
              write(*,'(1x,a,i8.8)') '.... bhash = ', bk.bhash
              segdes, bk*NOMOD
            endif
          end do
    
          write(*,'(1x)')
          write(*,'(1x,a)') '-- users --'
          do iur=1, urcnt
            ur = mypnt(lib,lb.uref(iur))
            segact, ur
            write(*,'(1x)')
            write(*,'(1x,a,i8.8)')'user:  index = ', iur
            write(*,'(1x,a,a)')   '....... name = ', ur.uname
    
    c print the books borrowed by the user
            ubbcnt = ur.ubb(/1)
            do ibor=1,ubbcnt
              bk = mypnt(lib,lb.bref(ur.ubb(ibor)))
              segact, bk
    
              write(*,'(1x)')
              write(*,'(1x,a,a)')    '>> borrowed book: title = ',
         &    bk.btitle
              write(*,'(1x,a,i4)')   '..................pages = ',
         &    bk.bpages
              write(*,'(1x,a,f7.2)')  '.................. udc = ',
         &    bk.budc
              write(*,'(1x,a,i8.8)') '..................bsize = ',
         &    bk.bepub(/1)
              write(*,'(1x,a,i8.8)') '..................bhash = ',
         &    bk.bhash
    
              segdes, bk*NOMOD
            end do
    
            segdes, ur*NOMOD
          end do
    
    c print the user who borrowed books and the indices of borrowed books
          write(*,'(1x)')
          write(*,'(1x,a)') '-- borrowed books by users --'
          do iur=1, urcnt
            ur = mypnt(lib,lb.uref(iur))
            segact, ur
            ubbcnt = ur.ubb(/1)
              do ibor=1, ubbcnt
                write(*,'(1x)')
                write(*,'(1x,a,i8.8)') 'user:    index = ', iur
                write(*,'(1x,a,a)')    '..........name = ', ur.uname
                write(*,'(1x,a,i8.8)') '... book index = ', ur.ubb(ibor)
              end do
            segdes, ur*NOMOD
          end do
    
    c desactivate head segment
          segdes, lb*NOMOD
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
           write(*,'(1x,a)') 'prtlib: end'
          end

16. relbk.E
    subroutine relbk(lib, name, title, verbose)
    implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    #include "user.seg"
    
    c arguments
           pointeur lib.PSTR
           character *(*) name
           character *(*) title
           logical verbose
    
    c external functions
           external mypnt
           integer mypnt
    
           external fndbk
           integer fndbk
    
           external fndur
           integer fndur
    
    c local variables
           integer libeta
    
           pointeur lb.tlib
           pointeur ur.user
           pointeur bk.book
    
           integer iur
           integer ir
           integer ir2
           integer jr
           integer ibk
    
           if (verbose) write(*,'(1x,a)') 'relbk: begin'
    
           if (verbose) then
             write(*,'(1x, a, a, a, a)')
         &   'relbk: user ', trim(name), ' is releasing book ', trim(title)
           endif
    
    c see whether the user exists in the structure
           iur = fndur(lib, name, .false.)
           if (iur .eq. 0) then
             write(*,'(1x,a,a)') 'cannot find user ', name
             return
           endif
           if (verbose) write(*,'(1x,a,i8.8)') 'borbk: iur = ', iur
    
    c see whether the book exists in the structure
           ibk = fndbk(lib, title, .false.)
           if (ibk .eq. 0) then
             write(*,'(1x,a,a)') 'cannot find book ', title
             return
           endif
           if (verbose) write(*,'(1x,a,i8.8)') 'borbk: ibk = ', ibk
    
    c activate the structure
           call oooeta(lib, libeta)
           call actstr(lib)
    
           lb = mypnt(lib,1)
           segact, lb
           brcnt = lb.bref(/1)
           urcnt = lb.uref(/1)
    
    c update borrowed status of the book
           if (.not. lb.bstatu(ibk)) then
             write(*,'(1x,a,a)')
         &     'cannot release an not borrowed book ', title
             return
           else
             lb.bstatu(ibk) = .false.
           endif
    
    c update the borrowed books by the user
           ur = mypnt(lib, lb.uref(iur))
           segact, ur
           ubbcnt = ur.ubb(/1)
    
    c search for the book to remove
           ir = -1
           do ir2 = 1, ubbcnt
             if (ur.ubb(ir2) .eq. ibk) then
               ir = ir2
             end if
           end do
    
    c adjust the array of borrowed books
           do jr = ir , ubbcnt - 1
             ur.ubb(jr) = ur.ubb(jr + 1)
           end do
           ubbcnt = ubbcnt - 1
           segadj, ur
           segdes, ur*MOD
    
           segdes,lb*MOD
    
    c deactivate the structure if activated on entry
           if(libeta.ne.1) call desstr(lib,'MOD')
           if (verbose) write(*,'(1x,a)') 'relbk: end'
           end

17. remfbk.E
    subroutine remfbk(lib, bcnt)
    c     Remove 'bcnt' free books
    
          implicit none
    
    #include "PSTR.inc"
    
    c arguments
          pointeur lib.PSTR
          integer bcnt
    
          character*40 title
          integer ibk
          integer ierr
    
          write(*,'(1x,a)') 'remfbk: begin'
          write(*,'(1x,a,i8,a)') 'remove ', bcnt, ' free books ...'
    
          do ibk=1,bcnt
            call takfbk(lib, title, ierr)
            if ( ierr .eq. 0 ) then
                call delfbk(lib, title, .false.)
            endif
          enddo
          write(*,'(1x,a)') 'remfbk: end'
          end
          
18. stopwatch.E
    subroutine stopwatch(time)
    c Like a 'stopwatch' or a 'chronometer' return elapsed time in seconds.
    c - On first call and any subsequent odd call => start the 'chronometer'.    
    c - On second call and any subsequent even call => stop the 'chronometer' and return the 'time'.   
          
          implicit none
          real time
          
          logical started
          
          integer clock_begin_count
          integer clock_end_count
          integer clock_rate
    
          save  clock_begin_count
          save  clock_rate
          
          save  started
          data started /.false./
          
          if ( .not. started ) then
            time = -1
            started = .true.
            call system_clock(clock_begin_count, clock_rate)
          
          else
            call system_clock(clock_end_count)
            time =  real(clock_end_count - clock_begin_count) / 
         &  real(clock_rate)
         
            started = .false.
          endif
          
          end

19. takbor.E
    subroutine takbor(lib, name, title, ierr)
    c     Randomly take a borrowed book 'title' by a user 'name' 
    
    c     >> implicit none
    c     >> 'implicit none' is put off in purpose of exercising the transpiler
          implicit integer (b)
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    #include "user.seg"
    
    c arguments
          pointeur lib.pstr
          character*(*) name
          character*(*) title
          integer ierr 
    
    c external functions
          external mypnt
          integer mypnt
          real myunif
          external myunif
         
    c local variables
          integer libeta
          pointeur ur.user
          pointeur bk.book
          pointeur lb.tlib
          
          integer ibor
          integer iur
          integer ibk
          integer ibk2
          integer ibbk
    
    c     >> integer bbkcnt
    c     >> 'bbkcnt' is not explicitly declared in purpose of exercising the transpiler
    
          real x 
           
          ierr = 0
          name = ''
          title = ''
          call oooeta(lib, libeta)
          call actstr(lib)
          lb = mypnt(lib,1)
          segact, lb       
          urcnt = lb.uref(/1)
          brcnt = lb.bref(/1)
          
          if ( brcnt .eq. 0) then
    c       == no books
            ierr = 1
          
          else
    c       -- count borrowed books
            bbkcnt = 0
            do ibk=1, brcnt
              if (lb.bref(ibk) .ne. 0 .and. lb.bstatu(ibk) ) then
                bbkcnt = bbkcnt + 1
              endif
            enddo
            
            if ( bbkcnt .eq. 0) then
    c           == no borrowed books
                ierr = 2
            
            else
    c           -- select a borrowed book
                x = myunif()
                ibbk = x*bbkcnt + 1
                
                ibk2 = 0
                bbkcnt = 0
                do ibk=1, brcnt
                    if (lb.bref(ibk) .ne. 0 .and. lb.bstatu(ibk)) then
                        bbkcnt = bbkcnt + 1
                        
                        if (bbkcnt .eq. ibbk) then
                            ibk2 = ibk
                            goto 100
                        endif
                    endif
                enddo
                
     100        continue
     
                if (ibk2 .eq. 0) then
                    write(*,'(1x,a)') 'takbor: (ibk2 .ne. 0) failed'
                    write(*,'(1x,a)') 'takbor: stop'
                    stop
                endif
                
                bk = mypnt(lib, lb.bref(ibk2))
                segact, bk
                title = bk.btitle
                segdes, bk*NOMOD
                
    c           -- find the user that borrowed the selected book
                do iur=1, urcnt
                  ur = mypnt(lib,lb.uref(iur))
                  segact, ur
                  ubbcnt = ur.ubb(/1)
                  do ibor=1,ubbcnt
                    if ( ur.ubb(ibor) .eq. ibk2) then
                        name = ur.uname
                        segdes, ur*NOMOD
                        goto 200
                    endif
                  end do
                  segdes, ur*NOMOD
                end do
     200        continue
            endif    
          endif
          segdes, lb*NOMOD
     
    c deactivate the structure if activated on entry
          if(libeta.ne.1) call desstr(lib,'MOD') 
          end
    
20. takfbk.E
    subroutine takfbk(lib, title, ierr)
    c     Randomly take a free book 'title' 
    
          implicit none
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "book.seg"
    
    c arguments
          pointeur lib.pstr
          character*(*) title
          integer ierr 
    
    c external functions
          external mypnt
          integer mypnt
    
          real myunif
          external myunif
         
    c local variables
          integer libeta
          
          pointeur bk.book
          pointeur lb.tlib
          
          integer ibk
          integer ibk2
          integer ifbk
          integer fbkcnt
          real x 
           
          ierr = 0
          title = ''
    
          call oooeta(lib, libeta)
          call actstr(lib)
          
          lb = mypnt(lib,1)
          segact, lb       
          urcnt = lb.uref(/1)
          brcnt = lb.bref(/1)
          
          if ( brcnt .eq. 0) then
    c       == no books
            ierr = 1
          
          else
    c       -- count free books
            fbkcnt = 0
            do ibk=1, brcnt
              if (lb.bref(ibk) .ne.0 .and. .not. lb.bstatu(ibk)) then
                fbkcnt = fbkcnt + 1
              endif
            enddo
            
            if ( fbkcnt .eq. 0) then
    c           == no free books
                ierr = 2
            
            else
    c           -- select a free book
                x = myunif()
                ifbk = x*fbkcnt + 1
                
                ibk2 = 0
                fbkcnt = 0
                do ibk=1, brcnt
                    if (lb.bref(ibk) .ne.0 .and. .not. lb.bstatu(ibk)) then
                        fbkcnt = fbkcnt + 1
                        
                        if (fbkcnt .eq. ifbk) then
                            ibk2 = ibk
                            goto 100
                        endif
                    endif
                enddo
                
     100        continue
     
                if (ibk2 .eq. 0) then
                    write(*,'(1x,a)') 'takfbk: (ibk2 .ne. 0) failed'
                    write(*,'(1x,a)') 'takfbk: stop'
                    stop
                endif
                
                bk = mypnt(lib, lb.bref(ibk2))
                segact, bk
                title = bk.btitle
                segdes, bk*NOMOD
            endif    
          endif
          segdes, lb*NOMOD
     
    c deactivate the structure if activated on entry
          if(libeta.ne.1) call desstr(lib,'MOD') 
          end
                 
21. takusr.E
    subroutine takusr(lib, name, ierr)
    c     Randomly take a user 'name'
    
    c     >> implicit none
    c     >> 'implicit none' is put off in purpose of exercising the transpiler
          implicit integer (i)
    
    #include "PSTR.inc"
    
    #include "tlib.seg"
    #include "user.seg"
    
    c arguments
          pointeur lib.pstr
          character*(*) name
          
    c     >> integer ierr
    c     >> 'ierr' is not explicitly declared in purpose of exercising the transpiler
    
    c external functions
          external mypnt
          integer mypnt
    
          real myunif
          external myunif
    
    c local variables
          integer libeta
    
          integer iur
          real x
    
          pointeur ur.user
          pointeur lb.tlib
    
          ierr = 0
          name = ''
    
          call oooeta(lib, libeta)
          call actstr(lib)
    
          lb = mypnt(lib,1)
          segact, lb
          urcnt = lb.uref(/1)
          brcnt = lb.bref(/1)
    
          if (urcnt .eq. 0) then
    c       == no users
            ierr = 1
    
          else
            x = myunif()
            iur = x*urcnt + 1
    
            ur = mypnt(lib, lb.uref(iur))
            segact, ur
            ubbcnt = ur.ubb(/1)
            name = ur.uname
            segdes, ur*NOMOD
          endif
    
     100  continue
          segdes, lb*NOMOD
    
    c deactivate the structure if activated on entry
          if(libeta.ne.1) call desstr(lib,'MOD')
          end
      
22. test_myunif.E
    subroutine test_myunif()
    
    c     -- Test the function 'myunif'
    
          implicit none
    
          real  myunif
          external  myunif
    
          integer test_iter
          integer test_count
          parameter(test_count=1000)
    
          integer print_count
          parameter(print_count=20)
    
          logical do_print
    
          real x
    
          write(*,'(1x,a)') 'test_myunif: begin'
    
          do test_iter=1, test_count
            x = myunif()
    
            do_print = .false.
    
            if ( test_iter .le. print_count/2 ) then
                do_print = .true.
    
            else if ( (test_count - test_iter) .le. print_count/2 ) then
                do_print = .true.
    
            else if ( .not. (x.ge.0 .and. x.lt.1) ) then
                do_print = .true.
            endif
    
            if ( do_print ) then
                write(*,'(1x, a, i4.4, a, f6.4)')
         &          'test_myunif: x(',
         &          test_iter, ') = ',
         &          x
            endif
          enddo
          write(*,'(1x,a)') 'test_myunif: end'
          end



Few-shot Examples: 


Example  ESOPE+Fortran:
subroutine chkout(repo, uname, btitle, dbgmode)
       implicit none
#include "HNDL.inc"
#include "dpool.seg"
#include "mbr.seg"
c arguments
       pointeur repo.HNDL
       character *(*) uname
       character *(*) btitle
       logical dbgmode
c external functions
       external getptr
       integer getptr
       external lkpbk
       integer lkpbk
       external lkpmbr
       integer lkpmbr
c local variables
       integer steta
       pointeur dp.dpool
       pointeur mp.mbr
       integer jbk
       integer jur
       if (dbgmode) write(*,'(1x, a)') 'chkout: begin'
       if (dbgmode) then
         write(*,'(1x, a, a, a, a)')
     &   'chkout: member ', trim(uname), ' is checking out item ', trim(btitle)
       endif
c see whether the member exists in the structure
       jur = lkpmbr(repo, uname, .false.)
       if (jur .eq. 0) then
         write(*,'(1x, a)') 'cannot find member ', uname
         return
       endif
       if (dbgmode) write(*,'(1x, a, i8.8)') 'chkout: jur = ', jur
c see whether the item exists in the structure
       jbk = lkpbk(repo, btitle, .false.)
       if (jbk .eq. 0) then
         write(*,'(1x, a, a)') 'cannot find item ', btitle
         return
       endif
       if (dbgmode) write(*,'(1x, a, i8.8)') 'chkout: jbk = ', jbk
c activate the structure
       call oooeta(repo, steta)
       call actstr(repo)
       dp = getptr(repo,1)
       segact, dp
       bkcnt = dp.bkref(/1)
       mbcnt = dp.mref(/1)
c update checked-out status of the item
       if (dp.ckdout(jbk)) then
         write(*,'(1x, a, a)')
     &    'cannot check out an already checked-out item ',
     &    btitle
         return
       else
         dp.ckdout(jbk) = .true.
       endif
c update the checked-out items by the member
       mp = getptr(repo, dp.mref(jur))
       segact, mp
       xbbcnt = mp.xbb(/1)
       xbbcnt = xbbcnt + 1
       segadj, mp
       mp.xbb(xbbcnt) = jbk
       segdes, mp*MOD
       segdes,dp*MOD
c deactivate the structure if activated on entry
       if(steta.ne.1) call desstr(repo,'MOD')
       if (dbgmode) write(*,'(1x, a)') 'chkout: end'
       end
       
       
Example  Fortran 2008:
module chkout_m
  use :: lkpmbr_m
  use :: dpool_m
  use :: hndl_m
  use :: mbr_m
  use :: lkpbk_m
implicit none
contains
subroutine chkout(repo, uname, btitle, dbgmode)
! [ooo] empty #include HNDL.inc
! [ooo] #include dpool.seg
integer :: bkcnt
integer :: mbcnt
! [ooo] #end-include dpool.seg
! [ooo] #include mbr.seg
integer :: xbbcnt
! [ooo] #end-include mbr.seg
!  arguments
type(hndl), pointer, intent(in) :: repo
character(len=*), intent(in) :: uname
character(len=*), intent(in) :: btitle
logical, intent(in) :: dbgmode
!  external functions
!  local variables
! [ooo].not-used: integer :: steta
type(dpool), pointer :: dp
type(mbr), pointer :: mp
integer :: jbk
integer :: jur
if (dbgmode) write (*, '(1x, a)') 'chkout: begin'
if (dbgmode) then
write (*, '(1x, a, a, a, a)') 'chkout: member ', trim(uname), ' is checking out item ', trim(btitle)
end if
!  see whether the member exists in the structure
    jur = lkpmbr(repo, uname, .false.)
if (jur == 0) then
write (*, '(1x, a)') 'cannot find member ', uname
return
end if
if (dbgmode) write (*, '(1x, a, i8.8)') 'chkout: jur = ', jur
!  see whether the item exists in the structure
    jbk = lkpbk(repo, btitle, .false.)
if (jbk == 0) then
write (*, '(1x, a, a)') 'cannot find item ', btitle
return
end if
if (dbgmode) write (*, '(1x, a, i8.8)') 'chkout: jbk = ', jbk
!  activate the structure
! [ooo].obsolete: call oooeta(repo,steta)
! [ooo].obsolete: call actstr(repo)
    dp => dpool_getptr(repo, 1)
! [ooo].obsolete: segact,dp
    bkcnt = size(dp % bkref, 1)
    mbcnt = size(dp % mref, 1)
!  update checked-out status of the item
if (dp % ckdout(jbk)) then
write (*, '(1x, a, a)') 'cannot check out an already checked-out item ', btitle
return
else
      dp % ckdout(jbk) = .true.
end if
!  update the checked-out items by the member
    mp => mbr_getptr(repo, dp % mref(jur))
! [ooo].obsolete: segact,mp
    xbbcnt = size(mp % xbb, 1)
    xbbcnt = xbbcnt + 1
call segadj(mp, xbbcnt)
    mp % xbb(xbbcnt) = jbk
! [ooo].obsolete: segdes,mp
! [ooo].obsolete: segdes,dp
!  deactivate the structure if activated on entry
! [ooo].empty-var: if (steta /= 1) ! [ooo].obsolete: call desstr(repo,'MOD')
if (dbgmode) write (*, '(1x, a)') 'chkout: end'
end subroutine chkout
end module chkout_m


IMPORTANT: You must respond ONLY with valid JSON in this exact format:
{
  "translated_code": "the translated Fortran 2008 code here"
}

Do not include any text before or after the JSON. Do not wrap the JSON in markdown code blocks.


"""


def extract_code_from_json(response_text):
    """
    Extract translated code from LLM response by parsing JSON.
    """
    response_text = response_text.strip()
    
    # Method 1: Direct JSON parse
    try:
        data = json.loads(response_text)
        if 'translated_code' in data:
            return data['translated_code'].strip()
    except json.JSONDecodeError:
        pass
    
    # Method 2: JSON in markdown blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, response_text, re.DOTALL)
    if matches:
        try:
            data = json.loads(matches[0])
            if 'translated_code' in data:
                return data['translated_code'].strip()
        except json.JSONDecodeError:
            pass
    
    # Method 3: Extract value using regex
    value_pattern = r'"translated_code"\s*:\s*"((?:[^"\\]|\\.)*)"'
    matches = re.findall(value_pattern, response_text, re.DOTALL)
    if matches:
        code = matches[0]
        code = code.replace('\\"', '"')
        code = code.replace('\\n', '\n')
        code = code.replace('\\t', '\t')
        return code.strip()
    
    # Method 4: Find JSON with brace matching
    if '"translated_code"' in response_text:
        brace_count = 0
        start_idx = -1
        
        for i, char in enumerate(response_text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    try:
                        json_str = response_text[start_idx:i+1]
                        data = json.loads(json_str)
                        if 'translated_code' in data:
                            return data['translated_code'].strip()
                    except json.JSONDecodeError:
                        continue
    
    # Method 5: Extract from code blocks
    code_pattern = r'```(?:fortran)?\s*(.*?)\s*```'
    code_matches = re.findall(code_pattern, response_text, re.DOTALL | re.IGNORECASE)
    if code_matches:
        return code_matches[0].strip()
    
    # Method 6: Strip JSON wrapper manually

    if response_text.startswith('{'):
        cleaned = re.sub(r'^\s*\{\s*"translated_code"\s*:\s*"', '', response_text)
        cleaned = re.sub(r'"\s*\}\s*$', '', cleaned)
        cleaned = cleaned.replace('\\"', '"')
        cleaned = cleaned.replace('\\n', '\n')
        cleaned = cleaned.replace('\\t', '\t')
        if cleaned != response_text and len(cleaned) > 0:
            return cleaned.strip()
    
    # Last resort
    return response_text.strip()



def translate_code(code_snippet, temperature=0.1, max_tokens=2048, top_p=1.0, max_retries=3, delay=1):
    """
    Calls the vLLM API to translate a single code snippet.
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user", 
                "content": f"Translate this legacy Fortran code to modern Fortran. Respond with JSON only.\n\nLegacy Code:\n{code_snippet}"
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            
            full_response = data['choices'][0]['message']['content']
            translated_code = extract_code_from_json(full_response)
            
            return translated_code
            
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                return f"Error translating: {str(e)}"
        except Exception as e:
            print(f"Unexpected error: {e}")
            return f"Error: {str(e)}"




def process_csv(input_file, output_file, legacy_col='legacy_code', 
                translated_col='translated_code', temperature=0.1, max_tokens=2048, top_p=1.0):
    """
    Process CSV file with code translation.
    """
    print(f"Loading: {input_file}")
    
    rows = []
    fieldnames = []
    
    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile, delimiter=';', restkey='extra_cols')
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    score_col = f"{translated_col}_score"
    
    if translated_col not in fieldnames:
        fieldnames.append(translated_col)
    if score_col not in fieldnames:
        fieldnames.append(score_col)

    for i, row in enumerate(rows):
        keys_to_fix = [k for k in row.keys() if k is None or k == 'extra_cols']
        for k in keys_to_fix:
            del row[k]

        legacy_code = row.get(legacy_col, '')
        
        if not legacy_code:
            row[translated_col] = ''
            row[score_col] = ''
            continue

        print(f"  [{i+1}/{len(rows)}] Translating for {translated_col}...")
        translated_code = translate_code(
            legacy_code, 
            temperature=temperature, 
            max_tokens=max_tokens,
            top_p=top_p
        )
        
        row[translated_col] = translated_code
        row[score_col] = ''

    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Successfully updated {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Translate Fortran code using vLLM API with JSON responses.'
    )
    parser.add_argument('input_csv', help='Path to the input CSV file')
    parser.add_argument('output_csv', help='Path to the output CSV file')
    parser.add_argument('--legacy-col', default='legacy_code', 
                        help='Column containing legacy code (default: legacy_code)')
    parser.add_argument('--translated-col', default='translated_code', 
                        help='Column for translated code (default: translated_code)')
    parser.add_argument('--temperature', type=float, default=0.1,
                        help='Temperature for generation (default: 0.1)')
    parser.add_argument('--max-tokens', type=int, default=2048,
                        help='Maximum tokens for generation (default: 2048)')
    parser.add_argument('--top-p', type=float, default=1.0,
                        help='Top-p (nucleus sampling) for generation (default: 1.0)')

    args = parser.parse_args()

    if not os.path.isfile(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' does not exist.")
        exit(1)

    process_csv(
        args.input_csv, 
        args.output_csv, 
        args.legacy_col, 
        args.translated_col,
        args.temperature,
        args.max_tokens,
        args.top_p
    )
